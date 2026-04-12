import asyncio
import json
import math
import os
import re

from aio_pika import logger
from application.const.sprint_generation import (
    API_VERB_METHOD_HINTS,
    EXTRACTION_CANONICAL_PHRASE_MAP,
    EXTRACTION_DOMAIN_VOCABULARY,
    API_ENDPOINT_FALLBACK_REGEX,
    API_METHOD_ENDPOINT_REGEX,
    DB_CONSTRAINT_TOKENS,
    EXTRACT_FILTER_API_FALLBACK_REGEX,
    EXTRACT_FILTER_API_STRICT_REGEX,
    EXTRACT_FILTER_BROKEN_ENDPOINT_REGEX,
    EXTRACT_FILTER_DB_COLUMN_REGEX,
    EXTRACT_FILTER_DB_CONSTRAINT_REGEX,
    EXTRACT_FILTER_FEATURE_NOISE_REGEX,
    EXTRACT_FILTER_JUNK_REGEX,
    EXTRACT_FILTER_MIN_TEXT_LENGTH,
    EXTRACT_FILTER_NOISE_BLACKLIST_REGEX,
    EXTRACT_FILTER_TASK_WEAK_VERB_ONLY_REGEX,
    EXTRACTION_SEMANTIC_DOMAIN_MIN_HIT_RATIO,
    EXTRACTION_SEMANTIC_ENTROPY_ENABLED,
    EXTRACTION_SEMANTIC_ENTROPY_MIN_TOKENS,
    EXTRACTION_SEMANTIC_ENTROPY_THRESHOLD,
    EXTRACTION_NOISE_TOKENS,
    FEATURE_HEADING_KEYWORDS,
    SignalOrigin,
    SignalType,
    SourceFileType,
    TASK_EXTRA_ACTION_PREFIXES,
    TASK_VERBS_EN,
    TASK_VERBS_VI,
    TYPE_BY_PREFIX,
    WINDOW_SCAN_SIZE,
    WINDOW_SCAN_STEP,
)
from application.dtos.sprint_generation_dto import ExtractionModelDTO, MarkdownFileDTO, SignalItemDTO
from domain.prompt.classify_and_extract_prompt import BuildClassifyAndExtractPrompt, BuildClassifyAndExtractRecoveryPrompt
from domain.prompt.translate_prompt import build_translate_prompt
from infrastructure.base.const.infra_const import LLMAgentName, LLMModel
from infrastructure.container import InfrastructureContainer


class ClassifyAndExtractPipeline:
    # Initialize dependencies and concurrency control so extraction can run per-file in parallel safely.
    def __init__(self, infra: InfrastructureContainer, max_concurrency: int = 5):
        self.llm = infra.get_llm_connector()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    # Run extraction for all files concurrently to keep throughput high for multi-file requests.
    async def classify_and_extract(self, file_dtos: list[MarkdownFileDTO]) -> list[ExtractionModelDTO]:
        tasks = [self._classify_one(file_dto) for file_dto in file_dtos]
        return await asyncio.gather(*tasks)

    # Execute one-file extraction pipeline with pattern-first baseline and AI refinement merge.
    async def _classify_one(self, file_dto: MarkdownFileDTO) -> ExtractionModelDTO:
        async with self._semaphore:
            # Pattern-first pass (LLD-aligned).
            pattern_payload = await self._heuristic_extract_from_source(file_dto)
            pattern_payload = self._canonical_cleanup_payload(pattern_payload)

            # AI refinement pass.
            refined_payload = await self._refine_with_ai(file_dto, pattern_payload)
            refined_payload = self._canonical_cleanup_payload(refined_payload)

            base_type = self._resolve_type(file_dto.file_name, refined_payload.get("type") or pattern_payload.get("type"))
            features = refined_payload.get("features", [])
            apis = refined_payload.get("apis", [])
            db_schema = refined_payload.get("db_schema", [])
            explicit_tasks = refined_payload.get("tasks", [])

            if base_type == "Requirement":
                derived_tasks = self._derive_tasks(apis=[], db_schema=[], features=features)
            else:
                derived_tasks = self._derive_tasks(apis=apis, db_schema=db_schema, features=features)

            payload = {
                "file_name": file_dto.file_name,
                "type": base_type,
                "features": features,
                "tasks": self._merge_by_key(explicit_tasks, derived_tasks, key="title"),
                "apis": apis,
                "db_schema": db_schema,
            }
            payload = self._canonical_cleanup_payload(payload)
            payload = self._apply_rule_based_hard_filter(payload)

            source_type = self._resolve_type(file_dto.file_name, payload.get("type"))
            return self._to_extraction_model(
                file_name=file_dto.file_name,
                source_type=source_type,
                payload=payload,
            )

    # Translate source markdown into English and keep the same DTO shape for downstream extraction.
    async def _translate_file_to_english(self, file_dto: MarkdownFileDTO) -> MarkdownFileDTO:
        if not file_dto.content:
            return file_dto

        source_text = file_dto.content.decode("utf-8", errors="ignore").strip()
        if not source_text:
            return file_dto

        prompt = build_translate_prompt([source_text], target_language="English")

        try:
            response_text = await self.llm.generate(
                prompt=prompt,
                model=LLMModel.GEMINI_2_5_FLASH,
                afc_enabled=False,
                max_output_tokens=8192,
                timeout_seconds=90.0,
                temperature=0.0,
                top_p=0.1,
                top_k=1,
            )
            translated_text = self._extract_translated_text(response_text, fallback=source_text)
        except Exception:
            logger.exception("translation failed | file=%s | fallback=original_content", file_dto.file_name)
            return file_dto

        if not translated_text:
            return file_dto

        translated_bytes = translated_text.encode("utf-8")
        return MarkdownFileDTO(
            file_name=file_dto.file_name,
            object_key=file_dto.object_key,
            size=len(translated_bytes),
            content=translated_bytes,
        )

    # Parse translation response and safely fall back to source text when JSON payload is malformed.
    @classmethod
    def _extract_translated_text(cls, response_text: str, fallback: str) -> str:
        try:
            payload = cls._parse_llm_json(response_text)
        except ValueError:
            return fallback

        if not isinstance(payload, dict):
            return fallback

        translations = payload.get("translations")
        if isinstance(translations, list):
            for item in translations:
                if not isinstance(item, dict):
                    continue
                translated = str(item.get("translated") or "").strip()
                if translated:
                    return translated

        translated_single = str(payload.get("translated") or payload.get("translation") or "").strip()
        if translated_single:
            return translated_single

        return fallback

    # Ask the LLM to refine wording only for already-extracted signals; fallback to pattern payload on any structural drift.
    async def _refine_with_ai(self, file_dto: MarkdownFileDTO, pattern_payload: dict) -> dict:
        base_payload = self._canonical_cleanup_payload(pattern_payload)

        prompt = self._build_refinement_prompt(file_dto.file_name, base_payload, relaxed=False)
        try:
            response_text = await self.llm.generate_for_agent(
                prompt=prompt,
                agent_name=LLMAgentName.EXTRACTION,
                afc_enabled=False,
                max_output_tokens=6144,
            )
            payload = self._canonical_cleanup_payload(self._parse_llm_json(response_text))

            if self._is_valid_refinement_output(base_payload, payload):
                return payload

            logger.warning(
                "refinement output invalid structure detected | file=%s | retry=relaxed_prompt",
                file_dto.file_name,
            )

            recovery_prompt = self._build_refinement_prompt(file_dto.file_name, base_payload, relaxed=True)
            recovery_response_text = await self.llm.generate(
                prompt=recovery_prompt,
                model=LLMModel.GEMINI_2_5_FLASH,
                afc_enabled=False,
                max_output_tokens=6144,
                timeout_seconds=60.0,
                temperature=0.2,
                top_p=0.9,
                top_k=40,
            )
            recovery_payload = self._canonical_cleanup_payload(self._parse_llm_json(recovery_response_text))
            if self._is_valid_refinement_output(base_payload, recovery_payload):
                return recovery_payload
        except Exception:
            logger.exception("refinement failed | file=%s | fallback=pattern_payload", file_dto.file_name)

        return base_payload

    # Build refinement prompt by injecting deterministic detected_signals payload from pattern extraction.
    @staticmethod
    def _build_refinement_prompt(file_name: str, detected_payload: dict, relaxed: bool) -> str:
        prompt_template = BuildClassifyAndExtractRecoveryPrompt() if relaxed else BuildClassifyAndExtractPrompt()
        detected_signals = {
            "features": detected_payload.get("features", []) if isinstance(detected_payload.get("features"), list) else [],
            "tasks": detected_payload.get("tasks", []) if isinstance(detected_payload.get("tasks"), list) else [],
            "apis": detected_payload.get("apis", []) if isinstance(detected_payload.get("apis"), list) else [],
            "db_schema": detected_payload.get("db_schema", []) if isinstance(detected_payload.get("db_schema"), list) else [],
        }
        input_context = {
            "uri": file_name,
            "mime": "text/markdown",
            "detected_signals": detected_signals,
        }
        return f"{prompt_template}\n\nINPUT_CONTEXT_JSON:\n{json.dumps(input_context)}"

    # Ensure AI refinement does not change structure or immutable fields; only wording is allowed.
    @classmethod
    def _is_valid_refinement_output(cls, original: dict, candidate: dict) -> bool:
        if not isinstance(original, dict) or not isinstance(candidate, dict):
            return False

        if str(candidate.get("type") or "").strip() and str(original.get("type") or "").strip():
            if str(candidate.get("type") or "").strip() != str(original.get("type") or "").strip():
                return False

        for bucket in ("features", "tasks", "apis", "db_schema"):
            left = original.get(bucket, [])
            right = candidate.get(bucket, [])
            if not isinstance(left, list) or not isinstance(right, list):
                return False
            if len(left) != len(right):
                return False

        for left, right in zip(original.get("tasks", []), candidate.get("tasks", [])):
            if str((left or {}).get("related_feature") or "").strip().casefold() != str((right or {}).get("related_feature") or "").strip().casefold():
                return False
            if str((left or {}).get("signal_origin") or "").strip().casefold() != str((right or {}).get("signal_origin") or "").strip().casefold():
                return False

        for left, right in zip(original.get("apis", []), candidate.get("apis", [])):
            left_endpoint = cls._normalize_endpoint(str((left or {}).get("endpoint") or ""))
            right_endpoint = cls._normalize_endpoint(str((right or {}).get("endpoint") or ""))
            if left_endpoint != right_endpoint:
                return False
            if str((left or {}).get("method") or "").strip().upper() != str((right or {}).get("method") or "").strip().upper():
                return False
            if str((left or {}).get("signal_origin") or "").strip().casefold() != str((right or {}).get("signal_origin") or "").strip().casefold():
                return False

        for left, right in zip(original.get("db_schema", []), candidate.get("db_schema", [])):
            if str((left or {}).get("table") or "").strip().casefold() != str((right or {}).get("table") or "").strip().casefold():
                return False
            if cls._format_db_columns((left or {}).get("columns") if isinstance((left or {}).get("columns"), list) else []) != cls._format_db_columns((right or {}).get("columns") if isinstance((right or {}).get("columns"), list) else []):
                return False
            if str((left or {}).get("signal_origin") or "").strip().casefold() != str((right or {}).get("signal_origin") or "").strip().casefold():
                return False

        return True

    # Canonical cleanup pass for extraction payload before and after AI refinement merge.
    @classmethod
    def _canonical_cleanup_payload(cls, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return cls._empty_payload("unknown")

        cleaned_features = [
            item
            for item in (cls._canonicalize_feature(item) for item in payload.get("features", []))
            if item is not None
        ]
        cleaned_tasks = [
            item
            for item in (cls._canonicalize_task(item) for item in payload.get("tasks", []))
            if item is not None
        ]
        cleaned_apis = [
            item
            for item in (cls._canonicalize_api(item) for item in payload.get("apis", []))
            if item is not None
        ]
        cleaned_apis = cls._dedupe_apis_by_signature(cleaned_apis)
        cleaned_apis = cls._drop_endpoint_only_when_method_exists(cleaned_apis)
        cleaned_db = [
            item
            for item in (cls._canonicalize_db_schema(item) for item in payload.get("db_schema", []))
            if item is not None
        ]

        return {
            "file_name": payload.get("file_name"),
            "type": payload.get("type"),
            "features": cls._dedupe_by_key(cleaned_features, "title"),
            "tasks": cls._dedupe_by_key(cleaned_tasks, "title"),
            "apis": cls._dedupe_by_key(cleaned_apis, "name"),
            "db_schema": cls._dedupe_by_key(cleaned_db, "table"),
        }

    # Canonicalize one feature item with strict deterministic title/description cleanup.
    @classmethod
    def _canonicalize_feature(cls, item: object) -> dict | None:
        if not isinstance(item, dict):
            return None

        title = cls._normalize_title(str(item.get("title") or ""))
        if not cls._is_valid_title(title):
            return None

        description = cls._normalize_description(str(item.get("description") or ""), title=title)
        return {
            "title": title,
            "description": description,
        }

    # Canonicalize one task item and reject noisy/broken titles deterministically.
    @classmethod
    def _canonicalize_task(cls, item: object) -> dict | None:
        if not isinstance(item, dict):
            return None

        title = cls._normalize_title(str(item.get("title") or ""))
        if not cls._is_valid_title(title):
            return None

        description = cls._normalize_description(str(item.get("description") or ""), title=title)
        related_feature = item.get("related_feature")
        if isinstance(related_feature, str):
            related_feature = cls._normalize_title(related_feature)
            if not related_feature:
                related_feature = None

        signal_origin = str(item.get("signal_origin") or "").strip() or None
        result = {
            "title": title,
            "description": description,
            "related_feature": related_feature,
        }
        if signal_origin:
            result["signal_origin"] = signal_origin
        return result

    # Canonicalize one API item with identifier cleanup and endpoint placeholder normalization.
    @classmethod
    def _canonicalize_api(cls, item: object) -> dict | None:
        if not isinstance(item, dict):
            return None

        endpoint = cls._normalize_endpoint(str(item.get("endpoint") or "")) or None
        method = str(item.get("method") or "").strip().upper() or None

        name_raw = str(item.get("name") or "")
        name = cls._normalize_title(name_raw)
        if not cls._is_valid_title(name):
            if method and endpoint:
                name = f"{method} {endpoint}".strip()
            elif endpoint:
                name = endpoint

        name = cls._normalize_title(name)
        if not cls._is_valid_title(name):
            # Keep endpoint-grounded API signals even when title tokenization is noisy.
            if endpoint and (
                re.search(EXTRACT_FILTER_API_FALLBACK_REGEX, endpoint, flags=re.IGNORECASE)
                or (method and re.search(EXTRACT_FILTER_API_STRICT_REGEX, f"{method} {endpoint}", flags=re.IGNORECASE))
            ):
                name = f"{method} {endpoint}".strip() if method else endpoint
            else:
                return None

        description = cls._normalize_description(str(item.get("description") or ""), title=name)
        return {
            "name": name,
            "endpoint": endpoint,
            "method": method,
            "description": description,
        }

    # Canonicalize one DB schema item and normalize table naming/description quality.
    @classmethod
    def _canonicalize_db_schema(cls, item: object) -> dict | None:
        if not isinstance(item, dict):
            return None

        table = cls._normalize_title(str(item.get("table") or ""))
        table = cls._normalize_db_identifier(table)
        if not cls._is_valid_title(table):
            return None

        columns = item.get("columns") if isinstance(item.get("columns"), list) else []
        cleaned_columns: list[dict] = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            col_name = cls._normalize_title(str(col.get("name") or ""))
            if not cls._is_valid_title(col_name):
                continue

            col_type = str(col.get("type") or "").strip() or None
            constraints = col.get("constraints") if isinstance(col.get("constraints"), list) else []
            cleaned_columns.append(
                {
                    "name": col_name,
                    "type": col_type,
                    "constraints": [str(c).strip() for c in constraints if str(c).strip()],
                }
            )

        return {
            "table": table,
            "columns": cleaned_columns,
        }

    # Validate one token using domain vocabulary and deterministic length/character rules.
    @staticmethod
    def _is_valid_token(token: str) -> bool:
        normalized = (token or "").strip().casefold()
        if not normalized:
            return False
        if normalized in EXTRACTION_DOMAIN_VOCABULARY:
            return True
        if normalized in EXTRACTION_NOISE_TOKENS:
            return False
        return normalized.isalpha() and len(normalized) >= 3

    # Extract Unicode letter tokens to keep Vietnamese diacritics in validation flow.
    @staticmethod
    def _extract_alpha_tokens(text: str) -> list[str]:
        return re.findall(r"[^\W\d_]+", text or "", flags=re.UNICODE)

    # Detect orphan suffix patterns like "for vi" and "for ch".
    @classmethod
    def _is_orphan_token_pattern(cls, title: str) -> bool:
        tokens = [token.casefold() for token in cls._extract_alpha_tokens(title)]
        for idx, token in enumerate(tokens[:-1]):
            if token != "for":
                continue
            tail = tokens[idx + 1:]
            if len(tail) != 1:
                continue
            candidate = tail[0]
            if len(candidate) <= 2:
                return True
            if not cls._is_valid_token(candidate):
                return True
        return False

    # Validate title after normalization with strict token and semantic-meaning checks.
    @classmethod
    def _is_valid_title(cls, title: str) -> bool:
        normalized = cls._normalize_title(title)
        if not normalized:
            return False
        if cls._is_orphan_token_pattern(normalized):
            return False

        tokens = [token.casefold() for token in cls._extract_alpha_tokens(normalized)]
        if not tokens:
            return False

        meaningful = False
        for token in tokens:
            if token in {"for", "to", "the", "and", "or", "of", "in", "on", "at", "by", "with", "from"}:
                continue
            if not cls._is_valid_token(token):
                # Ignore short/non-meaningful fragments such as version marker "v" in API paths.
                if len(token) <= 2:
                    continue
                return False
            if token in EXTRACTION_DOMAIN_VOCABULARY or len(token) >= 4:
                meaningful = True

        return meaningful

    # Normalize title text by removing markdown artifacts, numbering prefixes, and weak noise tokens.
    @classmethod
    def _normalize_title(cls, text: str) -> str:
        value = str(text or "").strip()
        if not value:
            return ""

        value = value.replace("\\_", "_").replace("\\-", "-")
        value = re.sub(r"[`*_~]+", "", value)
        value = re.sub(r"^\d+(?:\.\d+)*\s*", "", value)
        value = cls._split_identifier(value)
        value = re.sub(r"\s+", " ", value).strip(" .:-")

        lower_value = value.casefold()
        for raw_phrase, canonical in EXTRACTION_CANONICAL_PHRASE_MAP.items():
            pattern = re.compile(rf"\b{re.escape(raw_phrase)}\b", flags=re.IGNORECASE)
            lower_value = pattern.sub(canonical.casefold(), lower_value)

        tokens = lower_value.split()
        filtered_tokens: list[str] = []
        for token in tokens:
            if token in EXTRACTION_NOISE_TOKENS:
                continue
            filtered_tokens.append(token)

        if not filtered_tokens:
            return ""

        rebuilt = " ".join(filtered_tokens)
        rebuilt = re.sub(r"\s+", " ", rebuilt).strip()

        # Preserve known acronyms in uppercase after normalization.
        words = []
        for token in rebuilt.split():
            if token in EXTRACTION_DOMAIN_VOCABULARY:
                words.append(token.upper())
            else:
                words.append(token.capitalize())
        return " ".join(words)

    # Normalize and canonicalize free-text description while keeping deterministic semantics.
    @classmethod
    def _normalize_description(cls, description: str, title: str) -> str | None:
        raw = str(description or "").strip()
        if raw:
            raw = raw.replace("\\_", "_").replace("\\-", "-")
            raw = re.sub(r"[`*_~]+", "", raw)
            raw = re.sub(r"\s+", " ", raw).strip()
            if cls._is_valid_title(raw):
                if raw.casefold() == title.casefold():
                    return cls._default_description_for_title(title)
                return raw

        return cls._default_description_for_title(title)

    # Produce deterministic fallback description when source description is weak or noisy.
    @staticmethod
    def _default_description_for_title(title: str) -> str:
        lowered = (title or "").casefold()
        if "database schema" in lowered:
            return "Design database schema for system persistence layer"
        if "database migration" in lowered:
            return "Create database migration for schema evolution and versioning"
        if "request" in lowered:
            return f"Handle request for {lowered}"
        return f"Implement {title}" if title else ""

    # Normalize endpoint strings by removing duplicate slashes and standardizing placeholder formatting.
    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        value = str(endpoint or "").strip()
        if not value:
            return ""

        value = value.replace("\\", "_")
        value = re.sub(r"\{([^{}]+)_id\}", r"{\1_id}", value)
        value = re.sub(r"\{([^{}]+)id\}", r"{\1_id}", value)
        value = re.sub(r"/{2,}", "/", value)
        return value

    # Normalize identifier-like tokens by splitting camel case and replacing underscore separators.
    @staticmethod
    def _split_identifier(value: str) -> str:
        text = str(value or "")
        text = text.replace("_", " ")
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
        text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
        return text

    # Normalize DB identifier titles into readable words for deterministic canonical naming.
    @classmethod
    def _normalize_db_identifier(cls, value: str) -> str:
        cleaned = cls._split_identifier(value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cls._normalize_title(cleaned)

    # Merge pattern and AI outputs with pattern-first priority to maximize recall and keep deterministic signals.
    def _merge_pattern_first(self, file_name: str, pattern_payload: dict, ai_payload: dict) -> dict:
        base_type = self._resolve_type(
            file_name,
            pattern_payload.get("type") or ai_payload.get("type"),
        )

        features = self._merge_by_key(
            pattern_payload.get("features", []),
            ai_payload.get("features", []),
            key="title",
        )
        apis = self._merge_by_key(
            pattern_payload.get("apis", []),
            ai_payload.get("apis", []),
            key="name",
        )
        db_schema = self._merge_by_key(
            pattern_payload.get("db_schema", []),
            ai_payload.get("db_schema", []),
            key="table",
        )

        pattern_tasks = pattern_payload.get("tasks", [])
        ai_tasks = ai_payload.get("tasks", [])
        explicit_tasks = self._merge_by_key(pattern_tasks, ai_tasks, key="title")

        derived_tasks = self._derive_tasks(apis=apis, db_schema=db_schema, features=features)

        if base_type == "Planning" and pattern_tasks:
            tasks = self._merge_by_key(pattern_tasks, explicit_tasks + derived_tasks, key="title")
        elif base_type == "Requirement":
            tasks = self._merge_by_key(explicit_tasks, self._derive_tasks(apis=[], db_schema=[], features=features), key="title")
        else:
            tasks = self._merge_by_key(explicit_tasks, derived_tasks, key="title")

        return {
            "file_name": file_name,
            "type": base_type,
            "features": features,
            "tasks": tasks,
            "apis": apis,
            "db_schema": db_schema,
        }

    @staticmethod
    # Light dedupe helper: keep first occurrence by exact normalized key and preserve input order.
    def _merge_by_key(primary: list[dict], secondary: list[dict], key: str) -> list[dict]:
        merged: list[dict] = []
        seen: set[str] = set()

        for item in [*(primary or []), *(secondary or [])]:
            if not isinstance(item, dict):
                continue
            value = str(item.get(key) or "").strip().lower()
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            merged.append(item)

        return merged

    @staticmethod
    # Generate coverage tasks from detected API/DB/feature signals to avoid under-generation.
    def _derive_tasks(apis: list[dict], db_schema: list[dict], features: list[dict]) -> list[dict]:
        derived: list[dict] = []

        for api in apis:
            name = str(api.get("name") or "").strip()
            if not name:
                continue
            derived.append(
                {
                    "title": f"Implement {name}",
                    "description": f"Implement API {name}",
                    "related_feature": None,
                    "signal_origin": SignalOrigin.DERIVED.value,
                }
            )

        for table in db_schema:
            table_name = str(table.get("table") or "").strip()
            if not table_name:
                continue
            derived.append(
                {
                    "title": f"Design {table_name} schema",
                    "description": f"Design database schema for {table_name}",
                    "related_feature": None,
                    "signal_origin": SignalOrigin.DERIVED.value,
                }
            )
            derived.append(
                {
                    "title": f"Create migration for {table_name}",
                    "description": f"Create DB migration for {table_name}",
                    "related_feature": None,
                    "signal_origin": SignalOrigin.DERIVED.value,
                }
            )

        for feature in features:
            title = str(feature.get("title") or "").strip()
            if not title:
                continue
            derived.append(
                {
                    "title": f"Implement {title}",
                    "description": f"Implement feature {title}",
                    "related_feature": title,
                    "signal_origin": SignalOrigin.DERIVED.value,
                }
            )

        return derived

    @staticmethod
    # Detect sparse payloads so fallback strategies can run before returning low-signal outputs.
    def _is_effectively_empty(payload: dict) -> bool:
        if not isinstance(payload, dict):
            return True

        for key in ("features", "tasks", "apis", "db_schema"):
            value = payload.get(key)
            if isinstance(value, list) and len(value) > 0:
                return False
        return True

    @classmethod
    # Resolve file type deterministically from filename prefix, then fall back to AI type, then Planning.
    def _resolve_type(cls, file_name: str, llm_type: str | None) -> str:
        prefix_type = cls._type_from_file_prefix(file_name)
        if prefix_type:
            return prefix_type

        if llm_type in TYPE_BY_PREFIX.values():
            return llm_type

        return "Planning"

    @classmethod
    # Map known naming conventions (design/planning/requirement*) to normalized source type labels.
    def _type_from_file_prefix(cls, file_name: str) -> str | None:
        base_name = os.path.basename(file_name or "")
        stem_name = os.path.splitext(base_name)[0].strip().lower()

        for prefix, mapped_type in TYPE_BY_PREFIX.items():
            if stem_name == prefix:
                return mapped_type
            if stem_name.startswith(prefix):
                return mapped_type
            if stem_name.startswith(f"{prefix}-") or stem_name.startswith(f"{prefix}_") or stem_name.startswith(f"{prefix} "):
                return mapped_type

        return None

    @staticmethod
    # Parse the first valid JSON object from LLM text, including fenced blocks and sliced fallbacks.
    def _parse_llm_json(response_text: str) -> dict:
        decoder = json.JSONDecoder()

        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL)
        for block in fenced_blocks:
            parsed = ClassifyAndExtractPipeline._decode_first_json_object(block, decoder)
            if parsed is not None:
                return parsed

        parsed = ClassifyAndExtractPipeline._decode_first_json_object(response_text, decoder)
        if parsed is not None:
            return parsed

        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            first_brace = response_text.find("{")
            last_brace = response_text.rfind("}")
            if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
                logger.error("Classification parse error | invalid JSON response")
                raise ValueError("LLM response is not valid JSON")

            json_slice = response_text[first_brace:last_brace + 1]
            try:
                return json.loads(json_slice)
            except json.JSONDecodeError as exc:
                logger.error("Classification parse error | invalid JSON slice")
                raise ValueError("LLM response JSON parse failed") from exc

    @staticmethod
    # Decode the first JSON object occurrence from arbitrary text content.
    def _decode_first_json_object(text: str, decoder: json.JSONDecoder) -> dict | None:
        if not text:
            return None

        candidate_starts = [idx for idx, ch in enumerate(text) if ch == "{"]
        for start in candidate_starts:
            try:
                parsed, _ = decoder.raw_decode(text, start)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    # Download and gate source content for heuristic extraction; currently supports markdown-like inputs.
    async def _heuristic_extract_from_source(self, file_dto: MarkdownFileDTO) -> dict:
        if not file_dto.content:
            return self._empty_payload(file_dto.file_name)

        text = file_dto.content.decode("utf-8", errors="ignore")
        return self._heuristic_extract_from_markdown(text, file_dto.file_name)

    @classmethod
    # Pattern-first markdown extractor: window scan, table/line/heading scans, then cleanup and grouping.
    def _heuristic_extract_from_markdown(cls, text: str, file_name: str) -> dict:
        if not text.strip():
            return cls._empty_payload(file_name)

        features: list[dict] = []
        tasks: list[dict] = []
        apis: list[dict] = []
        db_schema: list[dict] = []

        lines = [line.rstrip("\n") for line in text.splitlines()]
        current_heading = ""
        table_buffer: list[str] = []

        windows = cls._build_windows(lines)
        apis.extend(cls._scan_api_windows(windows))
        tasks.extend(cls._scan_task_windows(windows))
        db_schema.extend(cls._scan_db_windows(windows))

        def flush_table() -> None:
            nonlocal table_buffer, apis, db_schema, tasks
            if len(table_buffer) < 2:
                table_buffer = []
                return

            headers, rows = cls._parse_markdown_table(table_buffer)
            if not headers or not rows:
                table_buffer = []
                return

            lowered = [h.lower() for h in headers]

            if "method" in lowered and "endpoint" in lowered:
                method_idx = lowered.index("method")
                endpoint_idx = lowered.index("endpoint")
                name_idx = lowered.index("name") if "name" in lowered else -1
                desc_idx = lowered.index("description") if "description" in lowered else -1

                for row in rows:
                    method = cls._cell(row, method_idx)
                    endpoint = cls._cell(row, endpoint_idx)
                    if not method and not endpoint:
                        continue
                    api_name = cls._cell(row, name_idx) if name_idx >= 0 else None
                    if not api_name:
                        api_name = f"{method} {endpoint}".strip() or endpoint or "api"
                    apis.append(
                        {
                            "name": api_name,
                            "endpoint": endpoint or None,
                            "method": method.upper() if method else None,
                            "description": cls._cell(row, desc_idx) if desc_idx >= 0 else None,
                        }
                    )

            if "column" in lowered and "type" in lowered:
                col_idx = lowered.index("column")
                type_idx = lowered.index("type")
                req_idx = lowered.index("required") if "required" in lowered else -1
                desc_idx = lowered.index("description") if "description" in lowered else -1

                table_name = cls._infer_table_name_from_heading(current_heading)
                columns: list[dict] = []
                for row in rows:
                    col_name = cls._cell(row, col_idx)
                    if not col_name:
                        continue

                    constraints: list[str] = []
                    required = cls._cell(row, req_idx) if req_idx >= 0 else ""
                    desc = cls._cell(row, desc_idx) if desc_idx >= 0 else ""
                    combined = f"{required} {desc}".upper()
                    for token in DB_CONSTRAINT_TOKENS:
                        if token in combined:
                            constraints.append(token)

                    columns.append(
                        {
                            "name": col_name,
                            "type": cls._cell(row, type_idx) or None,
                            "constraints": constraints,
                        }
                    )

                if columns:
                    db_schema.append(
                        {
                            "table": table_name,
                            "columns": columns,
                        }
                    )

            if any(h in lowered for h in ("task", "task name", "assignee", "estimation", "estimate")):
                task_title_idx = -1
                for candidate in ("task", "task name", "title", "name"):
                    if candidate in lowered:
                        task_title_idx = lowered.index(candidate)
                        break

                desc_idx = lowered.index("description") if "description" in lowered else -1
                for row in rows:
                    title = cls._cell(row, task_title_idx) if task_title_idx >= 0 else ""
                    if not title:
                        continue
                    desc = cls._cell(row, desc_idx) if desc_idx >= 0 else None
                    tasks.append(
                        {
                            "title": title,
                            "description": desc or f"Implement {title}",
                            "related_feature": None,
                        }
                    )

            table_buffer = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("#"):
                flush_table()
                current_heading = re.sub(r"^#+\s*", "", stripped).strip()
                if cls._is_feature_heading(current_heading):
                    features.append({"title": cls._normalize_heading(current_heading), "description": None})
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                table_buffer.append(stripped)
                continue

            if table_buffer and stripped == "":
                flush_table()
                continue

            api_match = re.search(API_METHOD_ENDPOINT_REGEX, stripped, flags=re.IGNORECASE)
            if api_match:
                method = (api_match.group(1) or "").upper()
                endpoint = (api_match.group(2) or "").strip()
                apis.append(
                    {
                        "name": f"{method} {endpoint}".strip(),
                        "endpoint": endpoint or None,
                        "method": method or None,
                        "description": None,
                    }
                )

            endpoint_match = re.search(API_ENDPOINT_FALLBACK_REGEX, stripped, flags=re.IGNORECASE)
            if endpoint_match:
                endpoint = endpoint_match.group(0).strip()
                inferred_method = cls._infer_method_from_text(stripped)
                apis.append(
                    {
                        "name": f"{inferred_method} {endpoint}".strip() if inferred_method else endpoint,
                        "endpoint": endpoint,
                        "method": inferred_method,
                        "description": None,
                    }
                )

            if stripped.startswith("-") or stripped.startswith("*"):
                bullet = stripped[1:].strip()
                if cls._looks_like_task(bullet):
                    tasks.append(
                        {
                            "title": bullet[:120],
                            "description": bullet,
                            "related_feature": None,
                        }
                    )

            inline_table_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)", stripped)
            if inline_table_match:
                table_name = inline_table_match.group(1).strip()
                db_schema.append(
                    {
                        "table": table_name,
                        "columns": [],
                    }
                )

        flush_table()

        features = cls._dedupe_by_key(features, "title")
        apis = cls._dedupe_by_key(apis, "name")
        db_schema = cls._dedupe_by_key(db_schema, "table")
        tasks = cls._dedupe_by_key(tasks, "title")

        return {
            "file_name": file_name,
            "type": cls._type_from_file_prefix(file_name) or "Design",
            "features": features,
            "tasks": tasks,
            "apis": apis,
            "db_schema": db_schema,
        }

    @staticmethod
    # Build overlapping windows to recover multi-line patterns such as split method/endpoint declarations.
    def _build_windows(lines: list[str]) -> list[str]:
        normalized = [line.strip() for line in lines if line and line.strip()]
        if len(normalized) < WINDOW_SCAN_SIZE:
            return ["\n".join(normalized)] if normalized else []

        windows: list[str] = []
        for i in range(0, len(normalized) - WINDOW_SCAN_SIZE + 1, WINDOW_SCAN_STEP):
            chunk = normalized[i:i + WINDOW_SCAN_SIZE]
            windows.append("\n".join(chunk))
        return windows

    @staticmethod
    # Detect API candidates from sliding windows using strong and fallback endpoint patterns.
    def _scan_api_windows(windows: list[str]) -> list[dict]:
        detected: list[dict] = []
        for window in windows:
            for match in re.finditer(API_METHOD_ENDPOINT_REGEX, window, flags=re.IGNORECASE):
                method = (match.group(1) or "").upper()
                endpoint = (match.group(2) or "").strip()
                if not endpoint:
                    continue
                detected.append(
                    {
                        "name": f"{method} {endpoint}",
                        "endpoint": endpoint,
                        "method": method or None,
                        "description": None,
                    }
                )
            for match in re.finditer(API_ENDPOINT_FALLBACK_REGEX, window, flags=re.IGNORECASE):
                endpoint = (match.group(0) or "").strip()
                if not endpoint:
                    continue
                inferred_method = ClassifyAndExtractPipeline._infer_method_from_text(window)
                detected.append(
                    {
                        "name": f"{inferred_method} {endpoint}".strip() if inferred_method else endpoint,
                        "endpoint": endpoint,
                        "method": inferred_method,
                        "description": None,
                    }
                )
        return detected

    @staticmethod
    # Detect action-oriented task candidates from window text using EN/VI verb patterns.
    def _scan_task_windows(windows: list[str]) -> list[dict]:
        task_regex = r"^(implement|build|create|add|design|update|delete|integrate|setup|configure)\b"
        verbs = set([*TASK_VERBS_EN, *TASK_VERBS_VI, *TASK_EXTRA_ACTION_PREFIXES])

        detected: list[dict] = []
        for window in windows:
            for line in window.splitlines():
                candidate = line.strip(" -*\t").strip()
                if not candidate:
                    continue
                lowered = candidate.lower()
                if re.match(task_regex, lowered):
                    detected.append(
                        {
                            "title": candidate[:120],
                            "description": candidate,
                            "related_feature": None,
                        }
                    )
                    continue
                if any(lowered.startswith(v) for v in verbs):
                    detected.append(
                        {
                            "title": candidate[:120],
                            "description": candidate,
                            "related_feature": None,
                        }
                    )
        return detected

    @staticmethod
    # Detect coarse database table hints from inline schema syntax in window text.
    def _scan_db_windows(windows: list[str]) -> list[dict]:
        detected: list[dict] = []
        for window in windows:
            inline_table_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)", window)
            if inline_table_match:
                detected.append(
                    {
                        "table": inline_table_match.group(1).strip(),
                        "columns": [],
                    }
                )
        return detected

    @staticmethod
    # Parse markdown table blocks into headers and data rows for structural signal extraction.
    def _parse_markdown_table(table_lines: list[str]) -> tuple[list[str], list[list[str]]]:
        rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in table_lines]
        if len(rows) < 2:
            return [], []

        headers = rows[0]
        data_rows = [row for row in rows[2:] if any(cell.strip() for cell in row)]
        return headers, data_rows

    @staticmethod
    # Safe cell accessor for variable-width table rows.
    def _cell(row: list[str], idx: int) -> str:
        if idx < 0 or idx >= len(row):
            return ""
        return row[idx].strip()

    @staticmethod
    # Infer stable table identifier from heading text when table names are implicit.
    def _infer_table_name_from_heading(heading: str) -> str:
        cleaned = re.sub(r"^\d+(\.\d+)*\s*", "", (heading or "")).strip()
        cleaned = re.sub(r"\s+", "_", cleaned.lower())
        cleaned = re.sub(r"[^\w]+", "", cleaned, flags=re.UNICODE)
        return cleaned or "table"

    @staticmethod
    # Normalize heading text for feature title use and deterministic dedupe.
    def _normalize_heading(heading: str) -> str:
        cleaned = re.sub(r"^\d+(\.\d+)*\s*", "", heading or "")
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    # Classify headings as feature-like using multilingual keyword lists from constants.
    def _is_feature_heading(heading: str) -> bool:
        text = (heading or "").lower()
        return any(keyword in text for keyword in FEATURE_HEADING_KEYWORDS)

    @staticmethod
    # Classify text as task-like using action-verb prefixes to maximize planning signal recall.
    def _looks_like_task(text: str) -> bool:
        value = (text or "").strip().lower()
        verbs = set([*TASK_VERBS_EN, *TASK_VERBS_VI, *TASK_EXTRA_ACTION_PREFIXES])
        return len(value) > 8 and any(value.startswith(v) for v in verbs)

    @staticmethod
    # Infer HTTP method for endpoint-only matches using EN/VI action hints in surrounding text.
    def _infer_method_from_text(text: str) -> str | None:
        lowered = (text or "").lower()
        for hint, method in API_VERB_METHOD_HINTS.items():
            if hint in lowered:
                return method
        return None

    @staticmethod
    # Exact-key dedupe helper used after scanning to keep noise controlled without semantic merging.
    def _dedupe_by_key(items: list[dict], key: str) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for item in items:
            value = str(item.get(key) or "").strip().lower()
            if not value:
                continue
            # Light dedupe: exact key match only.
            if value in seen:
                continue
            seen.add(value)
            result.append(item)
        return result

    @staticmethod
    # Deduplicate APIs by normalized (method, endpoint) signature before name-based dedupe.
    def _dedupe_apis_by_signature(items: list[dict]) -> list[dict]:
        result: list[dict] = []
        seen_signature: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            method = str(item.get("method") or "").strip().upper()
            endpoint = str(item.get("endpoint") or "").strip()
            if not endpoint:
                result.append(item)
                continue

            signature = f"{method} {endpoint}".strip().casefold()
            if signature in seen_signature:
                continue
            seen_signature.add(signature)
            result.append(item)

        return result

    @staticmethod
    # Drop method-less endpoint entries when the same endpoint already has a method-specific API entry.
    def _drop_endpoint_only_when_method_exists(items: list[dict]) -> list[dict]:
        endpoints_with_method = {
            str(item.get("endpoint") or "").strip().casefold()
            for item in items
            if isinstance(item, dict)
            and str(item.get("endpoint") or "").strip()
            and str(item.get("method") or "").strip()
        }

        result: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            endpoint = str(item.get("endpoint") or "").strip().casefold()
            method = str(item.get("method") or "").strip()
            if endpoint and not method and endpoint in endpoints_with_method:
                continue
            result.append(item)

        return result

    @staticmethod
    # Reject highly synthetic path segments that look like random mixed-case/hash-like tokens.
    def _looks_like_noise_endpoint(endpoint: str) -> bool:
        segments = [seg for seg in str(endpoint or "").strip().split("/") if seg]
        for seg in segments:
            if seg.lower() == "api" or re.fullmatch(r"v\d+", seg, flags=re.IGNORECASE):
                continue
            if seg.startswith("{") and seg.endswith("}"):
                continue

            if len(seg) >= 24 and re.search(r"[A-Z]", seg) and re.search(r"[a-z]", seg):
                return True
            if len(seg) >= 18 and re.search(r"\d", seg) and re.search(r"[A-Za-z]", seg) and "-" not in seg and "_" not in seg:
                return True

        return False

    @classmethod
    # Final deterministic gate: keep recall while dropping only obvious garbage signals.
    def _apply_rule_based_hard_filter(cls, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return cls._empty_payload("unknown")

        apis_in = payload.get("apis", [])
        db_in = payload.get("db_schema", [])
        features_in = payload.get("features", [])
        tasks_in = payload.get("tasks", [])

        apis = [api for api in apis_in if isinstance(api, dict) and cls._keep_api_signal(api)]
        apis = cls._dedupe_apis_by_signature(apis)
        apis = cls._drop_endpoint_only_when_method_exists(apis)
        db_schema = [db for db in db_in if isinstance(db, dict) and cls._keep_db_signal(db)]
        features = [feature for feature in features_in if isinstance(feature, dict) and cls._keep_feature_signal(feature)]
        tasks = [task for task in tasks_in if isinstance(task, dict) and cls._keep_task_signal(task)]

        return {
            "file_name": payload.get("file_name"),
            "type": payload.get("type"),
            "features": cls._dedupe_by_key(features, "title"),
            "tasks": cls._dedupe_by_key(tasks, "title"),
            "apis": cls._dedupe_by_key(apis, "name"),
            "db_schema": cls._dedupe_by_key(db_schema, "table"),
        }

    @classmethod
    def _keep_api_signal(cls, api: dict) -> bool:
        title = str(api.get("name") or "").strip()
        endpoint = str(api.get("endpoint") or "").strip()
        method = str(api.get("method") or "").strip()
        text = cls._signal_text(title, endpoint)

        if cls._is_too_short_or_junk(text):
            return False
        if cls._has_noise_blacklist(text):
            return False

        if endpoint and any(ch.isspace() for ch in endpoint):
            return False
        if endpoint and cls._looks_like_noise_endpoint(endpoint):
            return False

        strict_candidate = f"{method.upper()} {endpoint}".strip() if method and endpoint else title
        has_valid_api_shape = bool(re.fullmatch(EXTRACT_FILTER_API_STRICT_REGEX, strict_candidate, flags=re.IGNORECASE)) or bool(
            re.fullmatch(EXTRACT_FILTER_API_FALLBACK_REGEX, endpoint or title, flags=re.IGNORECASE)
        )
        if not has_valid_api_shape:
            return False

        # Reject endpoint-like values that are mostly isolated words with whitespace.
        if endpoint and re.match(EXTRACT_FILTER_BROKEN_ENDPOINT_REGEX, endpoint) and any(ch.isspace() for ch in endpoint):
            return False

        return True

    @classmethod
    def _keep_db_signal(cls, table: dict) -> bool:
        table_name = str(table.get("table") or "").strip()
        columns = table.get("columns") if isinstance(table.get("columns"), list) else []
        text = cls._signal_text(table_name, " ".join(cls._format_db_columns(columns)))

        if cls._is_too_short_or_junk(text):
            return False
        if cls._has_noise_blacklist(text):
            return False

        has_column_pattern = any(re.search(EXTRACT_FILTER_DB_COLUMN_REGEX, line, flags=re.IGNORECASE) for line in cls._format_db_columns(columns))
        has_constraint_pattern = any(
            re.search(EXTRACT_FILTER_DB_CONSTRAINT_REGEX, line, flags=re.IGNORECASE) for line in cls._format_db_columns(columns)
        )
        has_structured_columns = any(
            isinstance(col, dict)
            and str(col.get("name") or "").strip()
            and (str(col.get("type") or "").strip() or isinstance(col.get("constraints"), list))
            for col in columns
        )

        return has_structured_columns or has_column_pattern or has_constraint_pattern

    @classmethod
    def _keep_feature_signal(cls, feature: dict) -> bool:
        title = str(feature.get("title") or "").strip()
        desc = str(feature.get("description") or "").strip()
        text = cls._signal_text(title, desc)

        if cls._is_too_short_or_junk(text):
            return False
        if cls._has_noise_blacklist(text):
            return False
        if re.match(EXTRACT_FILTER_FEATURE_NOISE_REGEX, title, flags=re.IGNORECASE):
            return False
        if cls._has_high_semantic_entropy(text):
            return False

        return True

    @classmethod
    def _keep_task_signal(cls, task: dict) -> bool:
        title = str(task.get("title") or "").strip()
        desc = str(task.get("description") or "").strip()
        text = cls._signal_text(title, desc)

        if cls._is_too_short_or_junk(text):
            return False
        if cls._has_noise_blacklist(text):
            return False
        if re.match(EXTRACT_FILTER_TASK_WEAK_VERB_ONLY_REGEX, title, flags=re.IGNORECASE):
            return False
        if cls._has_high_semantic_entropy(text):
            return False

        return True

    @staticmethod
    def _signal_text(*parts: str) -> str:
        return " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())

    @staticmethod
    def _is_too_short_or_junk(text: str) -> bool:
        value = (text or "").strip()
        if len(value) < EXTRACT_FILTER_MIN_TEXT_LENGTH:
            return True
        return bool(re.match(EXTRACT_FILTER_JUNK_REGEX, value.casefold(), flags=re.IGNORECASE))

    @classmethod
    def _has_high_semantic_entropy(cls, text: str) -> bool:
        if not EXTRACTION_SEMANTIC_ENTROPY_ENABLED:
            return False

        tokens = [
            token
            for token in re.findall(r"[A-Za-z0-9_]+", str(text or "").casefold())
            if len(token) > 1
        ]
        if len(tokens) < EXTRACTION_SEMANTIC_ENTROPY_MIN_TOKENS:
            return False

        entropy = cls._semantic_entropy(tokens)
        if entropy <= EXTRACTION_SEMANTIC_ENTROPY_THRESHOLD:
            return False

        domain_hits = sum(1 for token in tokens if token in EXTRACTION_DOMAIN_VOCABULARY)
        hit_ratio = float(domain_hits / len(tokens)) if tokens else 0.0

        return hit_ratio < EXTRACTION_SEMANTIC_DOMAIN_MIN_HIT_RATIO

    @staticmethod
    def _semantic_entropy(tokens: list[str]) -> float:
        total = len(tokens)
        if total <= 0:
            return 0.0

        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1

        entropy = 0.0
        for count in counts.values():
            prob = count / total
            entropy -= prob * math.log2(prob)

        return entropy

    @staticmethod
    def _has_noise_blacklist(text: str) -> bool:
        return bool(re.search(EXTRACT_FILTER_NOISE_BLACKLIST_REGEX, (text or "").casefold(), flags=re.IGNORECASE))

    @staticmethod
    def _format_db_columns(columns: list[dict]) -> list[str]:
        lines: list[str] = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name") or "").strip()
            typ = str(col.get("type") or "").strip()
            constraints = col.get("constraints") if isinstance(col.get("constraints"), list) else []
            constraints_text = " ".join(str(c) for c in constraints if c)
            parts = [p for p in (name, f": {typ}" if typ else "", constraints_text) if p]
            if parts:
                lines.append(" ".join(parts).strip())
        return lines

    @classmethod
    # Convert legacy extraction payload buckets into flat LLD SignalItemDTO collections.
    def _to_extraction_model(cls, file_name: str, source_type: str, payload: dict) -> ExtractionModelDTO:
        file_type_enum = cls._to_source_file_type(source_type)

        api_items = [
            cls._build_signal_item(
                signal_type=SignalType.API,
                item_id=f"api-{idx}",
                title=str(api.get("name") or "").strip() or f"API {idx}",
                description=api.get("description"),
                file_name=file_name,
                file_type=file_type_enum,
                signal_origin=cls._resolve_signal_origin(api),
                metadata={
                    "endpoint": api.get("endpoint"),
                    "method": api.get("method"),
                },
            )
            for idx, api in enumerate(payload.get("apis", []), start=1)
            if isinstance(api, dict)
        ]

        db_items = [
            cls._build_signal_item(
                signal_type=SignalType.DATABASE,
                item_id=f"db-{idx}",
                title=str(table.get("table") or "").strip() or f"database-{idx}",
                description=None,
                file_name=file_name,
                file_type=file_type_enum,
                signal_origin=cls._resolve_signal_origin(table),
                metadata={
                    "columns": table.get("columns") if isinstance(table.get("columns"), list) else [],
                },
            )
            for idx, table in enumerate(payload.get("db_schema", []), start=1)
            if isinstance(table, dict)
        ]

        task_items = [
            cls._build_signal_item(
                signal_type=SignalType.TASK,
                item_id=f"task-{idx}",
                title=str(task.get("title") or "").strip() or f"task-{idx}",
                description=task.get("description"),
                file_name=file_name,
                file_type=file_type_enum,
                signal_origin=cls._resolve_signal_origin(task),
                metadata={
                    "related_feature": task.get("related_feature"),
                },
            )
            for idx, task in enumerate(payload.get("tasks", []), start=1)
            if isinstance(task, dict)
        ]

        feature_items = [
            cls._build_signal_item(
                signal_type=SignalType.FEATURE,
                item_id=f"feature-{idx}",
                title=str(feature.get("title") or "").strip() or f"feature-{idx}",
                description=feature.get("description"),
                file_name=file_name,
                file_type=file_type_enum,
                signal_origin=cls._resolve_signal_origin(feature),
                metadata={},
            )
            for idx, feature in enumerate(payload.get("features", []), start=1)
            if isinstance(feature, dict)
        ]

        return ExtractionModelDTO(
            api=api_items,
            databases=db_items,
            tasks=task_items,
            features=feature_items,
        )

    @staticmethod
    # Build one SignalItemDTO while dropping empty/null metadata values.
    def _build_signal_item(
        signal_type: SignalType,
        item_id: str,
        title: str,
        description: str | None,
        file_name: str,
        file_type: SourceFileType,
        signal_origin: SignalOrigin,
        metadata: dict,
    ) -> SignalItemDTO:
        clean_metadata = {k: v for k, v in metadata.items() if v not in (None, "", [], {})}
        return SignalItemDTO(
            item_id=item_id,
            signal_type=signal_type,
            signal_origin=signal_origin,
            title=title,
            description=description,
            source_file_name=file_name,
            source_file_type=file_type,
            metadata=clean_metadata,
        )

    @staticmethod
    def _resolve_signal_origin(item: dict) -> SignalOrigin:
        origin = str((item or {}).get("signal_origin") or "").strip().lower()
        if origin == SignalOrigin.DERIVED.value:
            return SignalOrigin.DERIVED
        if origin == SignalOrigin.INFERRED.value:
            return SignalOrigin.INFERRED
        return SignalOrigin.EXPLICIT

    @staticmethod
    # Normalize string source type into SourceFileType enum with safe Planning fallback.
    def _to_source_file_type(source_type: str) -> SourceFileType:
        mapping = {
            SourceFileType.PLANNING.value: SourceFileType.PLANNING,
            SourceFileType.REQUIREMENT.value: SourceFileType.REQUIREMENT,
            SourceFileType.DESIGN.value: SourceFileType.DESIGN,
        }
        return mapping.get(source_type, SourceFileType.PLANNING)

    @staticmethod
    # Return a schema-valid empty payload to keep downstream pipeline stable on extraction failures.
    def _empty_payload(file_name: str) -> dict:
        return {
            "file_name": file_name,
            "type": "Planning",
            "features": [],
            "tasks": [],
            "apis": [],
            "db_schema": [],
        }

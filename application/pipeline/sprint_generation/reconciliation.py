
import json
import logging
import re

from application.const.sprint_generation import (
    API_CONTRACT_ALLOWED_SIGNATURE_REGEX,
    API_CONTRACT_GATE_ENABLED,
    API_CONTRACT_ALLOW_ROOT,
    API_CONTRACT_METHODS,
    API_CONTRACT_MIN_SEGMENTS,
    API_CONTRACT_SIGNATURE_REGEX,
    API_NORMALIZATION_PARAM_PATTERNS,
    API_NORMALIZATION_PREFIX_PATTERNS,
    API_SEGMENT_ALIAS_ALLOWLIST,
    RECONCILIATION_API_ENDPOINT_EXTRACT_REGEX,
    RECONCILIATION_API_METHOD_ENDPOINT_PARSE_REGEX,
    RECONCILIATION_ID_TOKEN_REGEX,
    RECONCILIATION_MULTI_UNDERSCORE_REGEX,
    RECONCILIATION_NON_WORD_REGEX,
    RECONCILIATION_PLACEHOLDER_BLOCK_REGEX,
    RECONCILIATION_PLACEHOLDER_TRIM_REGEX,
    RECONCILIATION_SEGMENT_SANITIZE_REGEX,
    RECONCILIATION_SLASH_COLLAPSE_REGEX,
    RECONCILIATION_API_TITLE_ENDPOINT_ONLY_REGEX,
    RECONCILIATION_API_TITLE_WITH_METHOD_REGEX,
    RECONCILIATION_ALIAS_MAX_PER_ITEM,
    RECONCILIATION_ALIAS_NOISE_EXACT,
    RECONCILIATION_NOISE_PATTERNS,
    RECONCILIATION_ALIAS_TASK_LEADING_VERBS,
    RECONCILIATION_DOMAIN_VOCABULARY,
    RECONCILIATION_TITLE_NOISE_TOKENS,
    RECONCILIATION_VALID_TYPES,
    RECONCILIATION_VERSION_SEGMENT_REGEX,
    RECONCILIATION_WHITESPACE_REGEX,
    RECONCILIATION_WORD_TOKEN_REGEX,
    SignalOrigin,
    SourceFileType,
)
from application.dtos.sprint_generation_dto import (
    MergedItemDTO,
    NormalizationResultDTO,
    NormalizationSourceDTO,
    NormalizedItemDTO,
    ReconciliationOutputDTO,
)
from application.utils.time import timestamp_suffix
from domain.prompt.reconciliation_prompt import BuildReconciliationMergePrompt
from infrastructure.base.const.infra_const import LLMModel
from infrastructure.base.llm.gemini_llm import LLMConnector


class ReconciliationPipeline:
    _VALID_TYPES = RECONCILIATION_VALID_TYPES
    _MAX_ALIASES_PER_ITEM = RECONCILIATION_ALIAS_MAX_PER_ITEM
    _API_TITLE_WITH_METHOD_REGEX = re.compile(RECONCILIATION_API_TITLE_WITH_METHOD_REGEX, re.IGNORECASE)
    _API_TITLE_ENDPOINT_ONLY_REGEX = re.compile(RECONCILIATION_API_TITLE_ENDPOINT_ONLY_REGEX)

    def __init__(self, llm: LLMConnector, max_concurrency: int = 5):
        self.llm = llm
        self._max_concurrency = max_concurrency
    
    async def reconcile(
        self,
        data: NormalizationResultDTO,
    ) -> ReconciliationOutputDTO:
        collection_by_type: dict[str, list[NormalizedItemDTO]] = {
            "feature": data.features,
            "task": data.tasks,
            "api": data.apis,
            "db_schema": data.database,
        }

        cluster_map_by_type = {
            item_type: self._build_cluster_map(items)
            for item_type, items in collection_by_type.items()
        }

        ai_clusters_payload = self._build_ai_clusters_payload(cluster_map_by_type)
        merged_by_key = await self._merge_clusters_once(ai_clusters_payload, cluster_map_by_type)

        features = self._build_collection_result(
            item_type="feature",
            items=data.features,
            cluster_map=cluster_map_by_type["feature"],
            merged_by_key=merged_by_key,
        )
        tasks = self._build_collection_result(
            item_type="task",
            items=data.tasks,
            cluster_map=cluster_map_by_type["task"],
            merged_by_key=merged_by_key,
        )
        apis = self._build_collection_result(
            item_type="api",
            items=data.apis,
            cluster_map=cluster_map_by_type["api"],
            merged_by_key=merged_by_key,
        )
        apis = self._normalize_and_dedupe_api_items(apis)
        database = self._build_collection_result(
            item_type="db_schema",
            items=data.database,
            cluster_map=cluster_map_by_type["db_schema"],
            merged_by_key=merged_by_key,
        )

        result = ReconciliationOutputDTO(
            features=features,
            tasks=tasks,
            apis=apis,
            database=database,
        )
        return result

    # Apply structural API canonicalization and strict identity dedupe before downstream stages.
    def _normalize_and_dedupe_api_items(self, items: list[MergedItemDTO]) -> list[MergedItemDTO]:
        normalized: list[MergedItemDTO] = []
        seen: set[str] = set()

        for item in items:
            if item.type != "api":
                normalized.append(item)
                continue

            api_title = self._normalize_api_title(item.title)
            if not api_title:
                continue

            key = self._api_identity_key(api_title)
            if key in seen:
                continue

            if self._is_contract_filtered_out(key):
                continue

            seen.add(key)
            item.title = api_title
            normalized.append(item)

        return normalized

    @staticmethod
    def _is_contract_filtered_out(identity_key: str) -> bool:
        if not API_CONTRACT_GATE_ENABLED:
            return False

        text = str(identity_key or "").strip()
        if not text:
            return True

        if not re.fullmatch(API_CONTRACT_SIGNATURE_REGEX, text, flags=re.IGNORECASE):
            return True

        method, endpoint = text.split(" ", 1)
        method = method.upper().strip()
        endpoint = endpoint.strip()

        if method not in API_CONTRACT_METHODS:
            return True

        if endpoint == "/":
            return not API_CONTRACT_ALLOW_ROOT

        segments = [segment for segment in endpoint.split("/") if segment]
        if len(segments) < API_CONTRACT_MIN_SEGMENTS:
            return True

        if not API_CONTRACT_ALLOWED_SIGNATURE_REGEX:
            return False

        return not any(
            re.fullmatch(pattern, identity_key, flags=re.IGNORECASE)
            for pattern in API_CONTRACT_ALLOWED_SIGNATURE_REGEX
        )

    # Build a structural identity key for API titles so display placeholders can stay readable.
    def _api_identity_key(self, title: str) -> str:
        parsed = self._parse_method_endpoint(title)
        if parsed is None:
            endpoint = self._normalize_endpoint_for_identity(title)
            return endpoint.casefold()

        method, endpoint = parsed
        endpoint_norm = self._normalize_endpoint_for_identity(endpoint)
        return f"{method} {endpoint_norm}".strip().casefold()

    # Canonicalize API title as METHOD + normalized endpoint using structural rules only.
    def _normalize_api_title(self, title: str | None) -> str:
        parsed = self._parse_method_endpoint(title)
        if parsed is None:
            normalized = self.normalize_title(title)
            if self._API_TITLE_ENDPOINT_ONLY_REGEX.fullmatch(normalized):
                endpoint = self._normalize_endpoint_for_display(normalized)
                return endpoint
            return normalized

        method, endpoint = parsed
        endpoint_norm = self._normalize_endpoint_for_display(endpoint)
        return f"{method} {endpoint_norm}".strip()

    @staticmethod
    def _parse_method_endpoint(value: str | None) -> tuple[str, str] | None:
        text = str(value or "").strip()
        match = re.match(RECONCILIATION_API_METHOD_ENDPOINT_PARSE_REGEX, text, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).upper(), match.group(2)

    # Normalize endpoint identity with controlled prefix stripping and placeholder normalization.
    @staticmethod
    def _normalize_endpoint_for_identity(endpoint: str) -> str:
        value = str(endpoint or "").strip().lower()
        if not value:
            return ""

        value = re.sub(RECONCILIATION_SLASH_COLLAPSE_REGEX, "/", value)
        if not value.startswith("/"):
            value = f"/{value}"

        for pattern in API_NORMALIZATION_PREFIX_PATTERNS:
            candidate = re.sub(pattern, "", value)
            if candidate != value and candidate.startswith("/") and len(candidate) > 1:
                value = candidate
        if not value.startswith("/"):
            value = f"/{value}"

        segments = [segment for segment in value.split("/") if segment]
        normalized_segments: list[str] = []
        for segment in segments:
            if any(re.fullmatch(pattern, segment) for pattern in API_NORMALIZATION_PARAM_PATTERNS):
                normalized_segments.append("{}")
                continue
            normalized_segments.append(API_SEGMENT_ALIAS_ALLOWLIST.get(segment, segment))

        value = "/" + "/".join(normalized_segments)
        value = re.sub(RECONCILIATION_SLASH_COLLAPSE_REGEX, "/", value)
        return value or "/"

    # Normalize endpoint for display while preserving named placeholders (for readability).
    @staticmethod
    def _normalize_endpoint_for_display(endpoint: str) -> str:
        value = str(endpoint or "").strip().lower()
        if not value:
            return ""

        value = re.sub(RECONCILIATION_SLASH_COLLAPSE_REGEX, "/", value)
        if not value.startswith("/"):
            value = f"/{value}"

        for pattern in API_NORMALIZATION_PREFIX_PATTERNS:
            candidate = re.sub(pattern, "", value)
            if candidate != value and candidate.startswith("/") and len(candidate) > 1:
                value = candidate

        if not value.startswith("/"):
            value = f"/{value}"

        segments = [segment for segment in value.split("/") if segment]
        normalized_segments: list[str] = []
        for segment in segments:
            if any(re.fullmatch(pattern, segment) for pattern in API_NORMALIZATION_PARAM_PATTERNS):
                name = re.sub(RECONCILIATION_PLACEHOLDER_TRIM_REGEX, "", segment)
                name = re.sub(RECONCILIATION_SEGMENT_SANITIZE_REGEX, "_", name)
                name = re.sub(RECONCILIATION_MULTI_UNDERSCORE_REGEX, "_", name).strip("_") or "id"
                normalized_segments.append(f"{{{name}}}")
                continue

            normalized_segments.append(API_SEGMENT_ALIAS_ALLOWLIST.get(segment, segment))

        value = "/" + "/".join(normalized_segments)
        value = re.sub(RECONCILIATION_SLASH_COLLAPSE_REGEX, "/", value)
        return value or "/"

    @staticmethod
    def _build_cluster_map(items: list[NormalizedItemDTO]) -> dict[str, list[NormalizedItemDTO]]:
        cluster_map: dict[str, list[NormalizedItemDTO]] = {}
        for item in items:
            if ReconciliationPipeline._is_locked_planning_task(item):
                continue
            if item.cluster_id:
                cluster_map.setdefault(item.cluster_id, []).append(item)
        return cluster_map

    def _build_ai_clusters_payload(
        self,
        cluster_map_by_type: dict[str, dict[str, list[NormalizedItemDTO]]],
    ) -> list[dict]:
        payload: list[dict] = []
        for item_type, cluster_map in cluster_map_by_type.items():
            for cluster_id, items in cluster_map.items():
                # Validate titles before sending clusters to AI merge to reduce low-quality payloads.
                valid_items = [
                    item
                    for item in items
                    if self._is_valid_item_title(item_type, item.content.title)
                ]
                if len(valid_items) < 2:
                    continue
                payload.append(
                    {
                        "type": item_type,
                        "cluster_id": cluster_id,
                        "items": [
                            {
                                "title": self.normalize_title(item.content.title),
                                "description": item.content.description,
                                "source": {
                                    "file_name": item.source_file_name,
                                    "file_type": item.source_file_type.value,
                                },
                            }
                            for item in valid_items
                        ],
                    }
                )
        return payload

    async def _merge_clusters_once(
        self,
        ai_clusters_payload: list[dict],
        cluster_map_by_type: dict[str, dict[str, list[NormalizedItemDTO]]],
    ) -> dict[tuple[str, str], MergedItemDTO]:
        if not ai_clusters_payload:
            return {}

        merge_prompt = BuildReconciliationMergePrompt()
        merge_input_file = await self.llm.upload_file(
            object_key="reconciliation/batch_clusters.json" + timestamp_suffix(),
            content=json.dumps({"clusters": ai_clusters_payload}, ensure_ascii=False, indent=2).encode("utf-8"),
            mime="application/json",
        )

        merged_items: list[dict] = []
        try:
            response_text = await self.llm.generate(
                prompt=merge_prompt,
                model=LLMModel.GEMINI_3_0_FLASH,
                afc_enabled=False,
                files=[merge_input_file],
                max_output_tokens=6000,
                timeout_seconds=60.0,
                temperature=0.2,
                top_p=0.85,
                top_k=40,
            )
            llm_payload = self._parse_llm_json(response_text)
            merged_items = self._extract_merged_items(llm_payload)
        except Exception:
            logging.exception(
                "reconciliation batch merge failed - fallback to flash lite | clusters=%d",
                len(ai_clusters_payload),
            )
            try:
                response_text = await self.llm.generate(
                    prompt=merge_prompt,
                    model=LLMModel.GEMINI_3_1_FLASH_LITE,
                    afc_enabled=False,
                    files=[merge_input_file],
                    max_output_tokens=6000,
                    timeout_seconds=60.0,
                    temperature=0.2,
                    top_p=0.85,
                    top_k=40,
                )

                llm_payload = self._parse_llm_json(response_text)
                merged_items = self._extract_merged_items(llm_payload)
            except Exception:
                logging.exception(
                    "reconciliation batch merge failed on flash lite - fallback to heuristic | clusters=%d",
                    len(ai_clusters_payload),
                )
                return {}

        merged_by_key: dict[tuple[str, str], MergedItemDTO] = {}
        for merged in merged_items:
            if not isinstance(merged, dict):
                continue

            item_type = str(merged.get("type") or "").strip()
            cluster_id = str(merged.get("cluster_id") or "").strip()
            if item_type not in self._VALID_TYPES or not cluster_id:
                continue

            fallback_items = cluster_map_by_type.get(item_type, {}).get(cluster_id)
            if not fallback_items or len(fallback_items) < 2:
                continue

            merged_by_key[(item_type, cluster_id)] = self._to_merged_item_from_llm(
                expected_type=item_type,
                cluster_id=cluster_id,
                llm_payload=merged,
                fallback_items=fallback_items,
            )
        
        merged_count = len(merged_by_key)
        if merged_count == 0:
            return {}

        return merged_by_key

    @staticmethod
    def _extract_merged_items(llm_payload: dict) -> list[dict]:
        if "merged_items" in llm_payload and isinstance(llm_payload["merged_items"], list):
            return llm_payload["merged_items"]
        if "items" in llm_payload and isinstance(llm_payload["items"], list):
            return llm_payload["items"]
        if isinstance(llm_payload.get("clusters"), list):
            return llm_payload["clusters"]
        return []

    def _build_collection_result(
        self,
        item_type: str,
        items: list[NormalizedItemDTO],
        cluster_map: dict[str, list[NormalizedItemDTO]],
        merged_by_key: dict[tuple[str, str], MergedItemDTO],
    ) -> list[MergedItemDTO]:
        if not items:
            return []

        result: list[MergedItemDTO] = []
        emitted_clusters: set[str] = set()

        for item in items:
            if item_type == "task" and self._is_locked_planning_task(item):
                single_item = self._to_single_item(item_type, item)
                if single_item is not None:
                    result.append(single_item)
                continue

            cluster_id = item.cluster_id
            if not cluster_id:
                single_item = self._to_single_item(item_type, item)
                if single_item is not None:
                    result.append(single_item)
                continue

            cluster_items = cluster_map.get(cluster_id, [])
            if len(cluster_items) < 2:
                if cluster_id in emitted_clusters:
                    continue
                single_item = self._to_single_item(item_type, cluster_items[0] if cluster_items else item)
                if single_item is not None:
                    result.append(single_item)
                emitted_clusters.add(cluster_id)
                continue

            if cluster_id in emitted_clusters:
                continue

            merged_item = merged_by_key.get((item_type, cluster_id))
            if merged_item is None:
                merged_item = self._fallback_merge(item_type, cluster_id, cluster_items)
            if merged_item is not None:
                result.append(merged_item)
            emitted_clusters.add(cluster_id)

        return result

    # Preserve explicit planning tasks as user-intent signals: never merge or collapse them.
    @staticmethod
    def _is_locked_planning_task(item: NormalizedItemDTO) -> bool:
        return (
            item.type == "task"
            and item.source_file_type == SourceFileType.PLANNING
            and item.signal_origin == SignalOrigin.EXPLICIT
        )

    def _to_merged_item_from_llm(
        self,
        expected_type: str,
        cluster_id: str,
        llm_payload: dict,
        fallback_items: list[NormalizedItemDTO],
    ) -> MergedItemDTO | None:
        resolved_type = llm_payload.get("type")
        if resolved_type not in self._VALID_TYPES:
            resolved_type = expected_type
        if resolved_type != expected_type:
            resolved_type = expected_type

        title = (llm_payload.get("title") or "").strip()
        description = llm_payload.get("description")
        if isinstance(description, str):
            description = description.strip() or None
        else:
            description = None

        title = self.normalize_title(title)
        if not self._is_valid_item_title(expected_type, title):
            return self._fallback_merge(expected_type, cluster_id, fallback_items)

        aliases = self._generate_aliases(
            canonical_title=title,
            item_type=expected_type,
            max_aliases=self._MAX_ALIASES_PER_ITEM,
        )
        signal_origin = self._resolve_signal_origin(llm_payload.get("signal_origin"), fallback_items)

        sources_raw = llm_payload.get("source")
        if not isinstance(sources_raw, list):
            sources_raw = llm_payload.get("sources")
        sources = self._normalize_sources(sources_raw)

        if not sources:
            sources = self._collect_sources(fallback_items)

        primary_source = self._pick_primary_source(sources, fallback_items)

        return MergedItemDTO(
            id=f"{expected_type}:{cluster_id}",
            type=resolved_type,
            signal_origin=signal_origin,
            title=title,
            description=description,
            aliases=aliases,
            source_file_name=primary_source.file_name,
            source_file_type=self._to_source_file_type(primary_source.type),
            cluster_id=cluster_id,
        )

    def _fallback_merge(
        self,
        item_type: str,
        cluster_id: str,
        items: list[NormalizedItemDTO],
    ) -> MergedItemDTO | None:
        representative = self._select_representative_item(items, item_type)
        if representative is None:
            return None

        title = self.normalize_title(representative.content.title)
        if not self._is_valid_item_title(item_type, title):
            return None

        aliases = self._generate_aliases(
            canonical_title=title,
            item_type=item_type,
            max_aliases=self._MAX_ALIASES_PER_ITEM,
        )

        sources = self._collect_sources(items)
        primary_source = self._pick_primary_source(sources, items)

        return MergedItemDTO(
            id=f"{item_type}:{cluster_id}",
            type=item_type,
            signal_origin=self._dominant_signal_origin(items),
            title=title,
            description=representative.content.description,
            aliases=aliases,
            source_file_name=primary_source.file_name,
            source_file_type=self._to_source_file_type(primary_source.type),
            cluster_id=cluster_id,
        )

    def _to_single_item(self, item_type: str, item: NormalizedItemDTO) -> MergedItemDTO | None:
        title = self.normalize_title(item.content.title)
        if not self._is_valid_item_title(item_type, title):
            return None

        return MergedItemDTO(
            id=item.id,
            type=item_type,
            signal_origin=item.signal_origin,
            title=title,
            description=item.content.description,
            aliases=[],
            source_file_name=item.source_file_name,
            source_file_type=item.source_file_type,
            cluster_id=item.cluster_id,
        )

    # Select the best representative item with a valid normalized title for fallback merging.
    def _select_representative_item(self, items: list[NormalizedItemDTO], item_type: str) -> NormalizedItemDTO | None:
        valid_items = [
            item
            for item in items
            if self._is_valid_item_title(item_type, item.content.title)
        ]
        if not valid_items:
            return None

        return max(
            valid_items,
            key=lambda item: len(item.content.title or "") + len(item.content.description or ""),
        )

    # Validate titles by item type; APIs use endpoint-shape rules instead of generic token scoring.
    def _is_valid_item_title(self, item_type: str, title: str | None) -> bool:
        normalized = self.normalize_title(title)
        if not normalized:
            return False
        if item_type == "api":
            return self._is_valid_api_title(normalized)
        return self.is_valid_title(normalized)

    # Validate API titles deterministically by method/path shape while allowing versioned endpoints.
    def _is_valid_api_title(self, title: str) -> bool:
        normalized = self.normalize_title(title)
        if not normalized:
            return False

        if self._API_TITLE_WITH_METHOD_REGEX.fullmatch(normalized):
            return True
        if self._API_TITLE_ENDPOINT_ONLY_REGEX.fullmatch(normalized):
            return True
        return False

    @staticmethod
    def _pick_primary_source(
        sources: list[NormalizationSourceDTO],
        fallback_items: list[NormalizedItemDTO],
    ) -> NormalizationSourceDTO:
        if sources:
            return sources[0]

        if fallback_items:
            first = fallback_items[0]
            return NormalizationSourceDTO(
                file_name=first.source_file_name,
                type=first.source_file_type.value,
            )

        return NormalizationSourceDTO(file_name="unknown", type="Planning")

    @staticmethod
    def _to_source_file_type(raw_type: str) -> SourceFileType:
        normalized = str(raw_type or "").strip().lower()
        if normalized == "design":
            return SourceFileType.DESIGN
        if normalized == "requirement":
            return SourceFileType.REQUIREMENT
        return SourceFileType.PLANNING

    @staticmethod
    def _dominant_signal_origin(items: list[NormalizedItemDTO]) -> SignalOrigin:
        if not items:
            return SignalOrigin.EXPLICIT

        counts = {
            SignalOrigin.EXPLICIT: 0,
            SignalOrigin.DERIVED: 0,
            SignalOrigin.INFERRED: 0,
        }
        for item in items:
            counts[item.signal_origin] = counts.get(item.signal_origin, 0) + 1

        return max(counts.items(), key=lambda pair: pair[1])[0]

    @staticmethod
    def _resolve_signal_origin(raw_value: object, fallback_items: list[NormalizedItemDTO]) -> SignalOrigin:
        raw = str(raw_value or "").strip().lower()
        if raw == SignalOrigin.DERIVED.value:
            return SignalOrigin.DERIVED
        if raw == SignalOrigin.INFERRED.value:
            return SignalOrigin.INFERRED
        if raw == SignalOrigin.EXPLICIT.value:
            return SignalOrigin.EXPLICIT
        return ReconciliationPipeline._dominant_signal_origin(fallback_items)

    # Generate aliases deterministically from canonical title only, with type-specific transforms.
    def _generate_aliases(self, canonical_title: str, item_type: str, max_aliases: int = 6) -> list[str]:
        title = self.normalize_title(canonical_title)
        if not title:
            return []

        aliases: list[str] = [title]
        if item_type == "api":
            aliases.extend(self._generate_api_aliases(title))
        elif item_type == "task":
            aliases.extend(self._generate_task_aliases(title))
        elif item_type == "db_schema":
            aliases.extend(self._generate_db_aliases(title))
        elif item_type == "feature":
            aliases.extend(self._generate_feature_aliases(title))

        # Keep aliases distinct from canonical title in output DTO.
        filtered = self._dedupe_and_limit(aliases, max_aliases=max_aliases + 1)
        title_key = self._normalize_key(title)
        return [alias for alias in filtered if self._normalize_key(alias) != title_key][:max_aliases]

    # Build API aliases by converting path-like titles into readable resource names.
    def _generate_api_aliases(self, title: str) -> list[str]:
        aliases: list[str] = []
        cleaned = self._strip_api_placeholders(title)
        if cleaned and cleaned != title:
            aliases.append(cleaned)

        endpoint_match = re.search(RECONCILIATION_API_ENDPOINT_EXTRACT_REGEX, cleaned)
        if not endpoint_match:
            return aliases

        endpoint = endpoint_match.group(1)
        endpoint = re.sub(RECONCILIATION_VERSION_SEGMENT_REGEX, "", endpoint, flags=re.IGNORECASE)
        endpoint = endpoint.replace("{", "").replace("}", "")
        parts = [part for part in endpoint.split("/") if part and part.lower() != "api"]
        parts = [part for part in parts if part.lower() != "id" and not re.fullmatch(r"[0-9]+", part)]
        if not parts:
            return aliases

        readable = " ".join(parts).replace("_", " ").replace("-", " ")
        readable = re.sub(RECONCILIATION_WHITESPACE_REGEX, " ", readable).strip()
        if readable:
            aliases.append(readable)
        return aliases

    # Build DB aliases by converting schema/table style names into readable table phrases.
    def _generate_db_aliases(self, title: str) -> list[str]:
        aliases: list[str] = []
        cleaned = self._strip_api_placeholders(title)
        readable = cleaned.replace("_", " ").replace("-", " ")
        readable = re.sub(RECONCILIATION_WHITESPACE_REGEX, " ", readable).strip()
        if readable:
            aliases.append(readable)
        if readable and not readable.lower().endswith("table"):
            aliases.append(f"{readable} table")
        return aliases

    # Build task aliases by stripping leading action verbs to produce condensed noun phrases.
    def _generate_task_aliases(self, title: str) -> list[str]:
        aliases: list[str] = []
        leading_verbs = set(RECONCILIATION_ALIAS_TASK_LEADING_VERBS)

        words = title.split()
        if len(words) <= 1:
            return aliases

        first_word_norm = words[0].strip().casefold()
        if first_word_norm in leading_verbs:
            condensed = " ".join(words[1:]).strip()
            if condensed:
                aliases.append(condensed)

        return aliases

    # Build feature aliases by structural normalization only.
    def _generate_feature_aliases(self, title: str) -> list[str]:
        return [title]

    # Deduplicate and limit aliases deterministically after strict validation.
    def _dedupe_and_limit(self, aliases: list[str], max_aliases: int) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for alias in aliases:
            cleaned = self.normalize_title(alias)
            key = self._normalize_key(cleaned)
            if not self._is_valid_alias(cleaned):
                continue
            if key in seen:
                continue

            seen.add(key)
            result.append(cleaned)
            if len(result) >= max_aliases:
                break

        return result

    # Remove API placeholders and IDs to avoid fragmented aliases from template endpoints.
    @staticmethod
    def _strip_api_placeholders(value: str) -> str:
        cleaned = value or ""
        cleaned = re.sub(RECONCILIATION_PLACEHOLDER_BLOCK_REGEX, "", cleaned)
        cleaned = re.sub(RECONCILIATION_ID_TOKEN_REGEX, "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(RECONCILIATION_WHITESPACE_REGEX, " ", cleaned).strip(" /:-")
        return cleaned

    # Detect fragmented aliases containing one-letter tokens that commonly come from LLM token artifacts.
    @staticmethod
    def _has_fragmented_tokens(value: str) -> bool:
        tokens = re.findall(RECONCILIATION_WORD_TOKEN_REGEX, value, flags=re.UNICODE)
        return any(len(token) == 1 for token in tokens)

    # Count meaningful alphanumeric characters for minimum-information alias validation.
    @staticmethod
    def _meaningful_char_count(value: str) -> int:
        return len(re.sub(RECONCILIATION_NON_WORD_REGEX, "", value or "", flags=re.UNICODE))

    # Build a deterministic case-insensitive key for text comparison and deduplication.
    @staticmethod
    def _normalize_key(value: str) -> str:
        return re.sub(RECONCILIATION_WHITESPACE_REGEX, " ", (value or "").strip()).casefold()

    # Normalize title text by removing markdown artifacts, numbering prefixes, and extra whitespace.
    def normalize_title(self, value: str | None) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        # Remove markdown wrappers and escaped punctuation from LLM output.
        text = re.sub(r"[`*_~]+", "", text)
        text = text.replace("\\.", ".").replace("\\-", "-")
        text = re.sub(r"^\W+", "", text)
        text = re.sub(r"^\d+(?:\.\d+)*\s*", "", text)
        text = re.sub(RECONCILIATION_WHITESPACE_REGEX, " ", text).strip(" .:-")

        return text

    # Validate one token using domain vocabulary first, then deterministic alphabetic length rules.
    @staticmethod
    def is_valid_token(token: str) -> bool:
        normalized = (token or "").strip().casefold()
        if not normalized:
            return False
        if normalized in RECONCILIATION_DOMAIN_VOCABULARY:
            return True
        return normalized.isalpha() and len(normalized) >= 3

    # Extract Unicode letter tokens to preserve Vietnamese words during title validation.
    @staticmethod
    def _extract_alpha_tokens(text: str) -> list[str]:
        return re.findall(r"[^\W\d_]+", text or "", flags=re.UNICODE)

    # Detect broken orphan suffix patterns like "for vi", "for ch", or "for <unknown-single-token>".
    def is_orphan_token_pattern(self, title: str) -> bool:
        normalized = self.normalize_title(title).casefold()
        tokens = [token.casefold() for token in self._extract_alpha_tokens(normalized)]
        for idx, token in enumerate(tokens[:-1]):
            if token != "for":
                continue
            tail = tokens[idx + 1:]
            if len(tail) != 1:
                continue
            candidate = tail[0]
            if len(candidate) <= 2:
                return True
            if candidate not in RECONCILIATION_DOMAIN_VOCABULARY:
                return True
        return False

    # Validate title by token quality, orphan suffix patterns, and meaningful-domain-token requirement.
    def is_valid_title(self, title: str) -> bool:
        normalized = self.normalize_title(title)
        if not normalized:
            return False
        normalized_key = self._normalize_key(normalized)
        if normalized_key in RECONCILIATION_ALIAS_NOISE_EXACT:
            return False
        if any(noise in normalized_key for noise in RECONCILIATION_NOISE_PATTERNS):
            return False
        if self.is_orphan_token_pattern(normalized):
            return False

        tokens = [token.casefold() for token in self._extract_alpha_tokens(normalized)]
        if not tokens:
            return False

        meaningful = False
        for token in tokens:
            if token in RECONCILIATION_TITLE_NOISE_TOKENS:
                continue
            if not self.is_valid_token(token):
                return False
            if token in RECONCILIATION_DOMAIN_VOCABULARY or len(token) >= 4:
                meaningful = True

        return meaningful

    # Validate aliases with minimum information and strict generic-noise rejection.
    def _is_valid_alias(self, text: str) -> bool:
        normalized = self.normalize_title(text)
        if not self.is_valid_title(normalized):
            return False
        if self._meaningful_char_count(normalized) < 4:
            return False
        if self._has_fragmented_tokens(normalized):
            return False
        if self._normalize_key(normalized) in RECONCILIATION_ALIAS_NOISE_EXACT:
            return False

        return True

    @staticmethod
    def _normalize_sources(raw_sources: object) -> list[NormalizationSourceDTO]:
        if not isinstance(raw_sources, list):
            return []

        unique: dict[tuple[str, str], NormalizationSourceDTO] = {}
        for src in raw_sources:
            if not isinstance(src, dict):
                continue
            file_name = str(src.get("file_name") or "").strip()
            file_type = str(src.get("file_type") or src.get("type") or "").strip()
            if not file_name or not file_type:
                continue

            key = (file_name, file_type)
            unique[key] = NormalizationSourceDTO(file_name=file_name, type=file_type)

        return sorted(unique.values(), key=lambda s: s.file_name.lower())

    def _collect_sources(self, items: list[NormalizedItemDTO]) -> list[NormalizationSourceDTO]:
        unique: dict[tuple[str, str], NormalizationSourceDTO] = {}
        for item in items:
            key = (item.source_file_name, item.source_file_type.value)
            unique[key] = NormalizationSourceDTO(
                file_name=item.source_file_name,
                type=item.source_file_type.value,
            )

        return sorted(unique.values(), key=lambda s: s.file_name.lower())

    @staticmethod
    def _parse_llm_json(response_text: str) -> dict:
        candidates = ReconciliationPipeline._collect_json_candidates(response_text)

        for candidate in candidates:
            parsed = ReconciliationPipeline._try_parse_json_candidate(candidate)
            if parsed is not None:
                return parsed

        repaired_candidates = [ReconciliationPipeline._repair_json_like_text(c) for c in candidates]
        for candidate in repaired_candidates:
            parsed = ReconciliationPipeline._try_parse_json_candidate(candidate)
            if parsed is not None:
                return parsed

        raise ValueError("LLM response is not valid JSON")

    @staticmethod
    def _collect_json_candidates(response_text: str) -> list[str]:
        candidates: list[str] = []

        # Prefer fenced payloads first when model wraps structured output in markdown.
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", response_text or "", re.DOTALL)
        for block in fenced_blocks:
            if block and block.strip():
                candidates.append(block.strip())

        if response_text and response_text.strip():
            candidates.append(response_text.strip())

        seen: set[str] = set()
        unique_candidates: list[str] = []
        for candidate in candidates:
            key = candidate.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_candidates.append(key)

        return unique_candidates

    @staticmethod
    def _try_parse_json_candidate(candidate: str) -> dict | None:
        if not candidate:
            return None

        try:
            parsed = json.loads(candidate)
            return ReconciliationPipeline._normalize_parsed_payload(parsed)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        parsed = ReconciliationPipeline._decode_first_json_value(candidate, decoder)
        if parsed is None:
            return None

        return ReconciliationPipeline._normalize_parsed_payload(parsed)

    @staticmethod
    def _decode_first_json_value(text: str, decoder: json.JSONDecoder) -> dict | list | None:
        if not text:
            return None

        candidate_starts = [idx for idx, ch in enumerate(text) if ch in "[{"]
        for start in candidate_starts:
            try:
                parsed, _ = decoder.raw_decode(text, start)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _normalize_parsed_payload(parsed: object) -> dict:
        if isinstance(parsed, list):
            return {"merged_items": parsed}
        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object")
        return parsed

    @staticmethod
    def _repair_json_like_text(text: str) -> str:
        if not text:
            return text

        repaired = text
        repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
        repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")

        # Remove trailing commas before object/array closures.
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

        # Convert raw newlines inside quoted strings to escaped \n for JSON compatibility.
        out: list[str] = []
        in_string = False
        escaped = False
        for ch in repaired:
            if escaped:
                out.append(ch)
                escaped = False
                continue

            if ch == "\\":
                out.append(ch)
                escaped = True
                continue

            if ch == '"':
                out.append(ch)
                in_string = not in_string
                continue

            if in_string and ch == "\n":
                out.append("\\n")
                continue

            if in_string and ch == "\r":
                continue

            out.append(ch)

        return "".join(out)
    
import json
import logging
import math
import re

from application.const.sprint_generation import (
    SignalOrigin,
    SourceFileType,
    TASK_DUE_DATE_REGEX,
    TASK_GENERATION_API_TASK_NAME_REGEX,
    TASK_GENERATION_BEHAVIOR_SUFFIX_REGEX,
    TASK_GENERATION_ENDPOINT_SLASH_COLLAPSE_REGEX,
    TASK_GENERATION_GENERIC_WORDS,
    TASK_GENERATION_JSON_FENCE_REGEX,
    TASK_GENERATION_METHOD_REWRITE_REGEX,
    TASK_GENERATION_ORIGIN_RANK,
    TASK_GENERATION_SOURCE_RANK,
    TASK_GENERATION_STOPWORDS,
    TASK_GENERATION_TASK_VERBS,
    TASK_SEMANTIC_DEDUP_ENABLED,
    TASK_SEMANTIC_DEDUP_MAX_TRY,
    TASK_GENERATION_TEXT_SANITIZE_REGEX,
    TASK_GENERATION_TOKEN_REGEX,
    TASK_GENERATION_VERIFY_PREFIX_REGEX,
    TASK_GENERATION_WHITESPACE_REGEX,
)
from application.dtos.sprint_generation_dto import (
    AISprintGenerationRequestedPayloadDTO,
    AISprintGenerationResultTaskDTO,
    CanonicalizationFeatureDTO,
    CanonicalizationItemDTO,
    CanonicalizationResultDTO,
    CoverageIssueDTO,
    CoverageSummaryDTO,
)
from application.utils.time import timestamp_suffix
from domain.prompt.task_generation_prompt import BuildTaskExpansionPrompt, BuildTaskGenerationPrompt
from infrastructure.base.const.infra_const import LLMAgentName, LLMModel
from infrastructure.base.llm.gemini_llm import LLMConnector


class TaskGenerationPipeline:
    _API_TASK_NAME_REGEX = re.compile(TASK_GENERATION_API_TASK_NAME_REGEX, flags=re.IGNORECASE)

    def __init__(self, llm: LLMConnector):
        self.llm = llm

    async def generate_tasks(
        self,
        canonicalization: CanonicalizationResultDTO,
        payload: AISprintGenerationRequestedPayloadDTO,
    ) -> list[AISprintGenerationResultTaskDTO]:
        primary_context = self._build_primary_context(canonicalization)
        target_min_tasks = self._compute_minimum_task_target(canonicalization)

        # Deterministic baseline keeps primary coverage even when LLM output is weak.
        deterministic_tasks = self._generate_deterministic_tasks(canonicalization, primary_context)

        prompt = BuildTaskGenerationPrompt(
            additional_context=payload.additional_context,
            sprint_name=payload.sprint.name,
            sprint_goal=payload.sprint.goal,
            sprint_start_date=payload.sprint.start_date,
            sprint_end_date=payload.sprint.end_date,
            target_min_tasks=target_min_tasks,
        )

        canonical_json = canonicalization.model_dump()
        uploaded_file = await self.llm.upload_file(
            object_key="task_generation/canonicalization_input.json",
            content=json.dumps(canonical_json, ensure_ascii=False, indent=2).encode("utf-8"),
            mime="application/json",
        )

        response_text = await self.llm.generate_for_agent(
            prompt=prompt,
            agent_name=LLMAgentName.TASK_GENERATION,
            afc_enabled=False,
            files=[uploaded_file],
            max_output_tokens=8192,
        )

        parsed_items = self._extract_tasks(self._parse_llm_json(response_text))
        llm_tasks = self._normalize_tasks(parsed_items)
        tasks = self._dedupe_tasks([*deterministic_tasks, *llm_tasks])

        if len(tasks) < target_min_tasks:
            expansion_prompt = BuildTaskExpansionPrompt(
                sprint_name=payload.sprint.name,
                sprint_goal=payload.sprint.goal,
                sprint_start_date=payload.sprint.start_date,
                sprint_end_date=payload.sprint.end_date,
                target_min_tasks=target_min_tasks,
                existing_tasks=[task.model_dump() for task in tasks],
            )

            expansion_response = await self.llm.generate_for_agent(
                prompt=expansion_prompt,
                agent_name=LLMAgentName.TASK_GENERATION,
                afc_enabled=False,
                files=[uploaded_file],
                max_output_tokens=8192,
            )

            extra_items = self._extract_tasks(self._parse_llm_json(expansion_response))
            extra_tasks = self._normalize_tasks(extra_items)
            tasks = self._dedupe_tasks([*tasks, *extra_tasks])

        # Bounded deterministic repair loop for missing coverage and source propagation issues.
        max_attempts = 2
        for _ in range(max_attempts + 1):
            issues, summary = self._validate_coverage(primary_context, tasks)
            if summary.error_count == 0:
                break

            repairs = self._repair_from_issues(primary_context, issues)
            if not repairs:
                break
            tasks = self._dedupe_tasks([*tasks, *repairs])

        # Last-line guarantee: if signals exist and tasks are still empty, emit deterministic fallback.
        if not tasks and self._has_any_signal(canonicalization):
            tasks = self._generate_deterministic_tasks(canonicalization, primary_context)
            tasks = self._dedupe_tasks(tasks)

        tasks = self._collapse_put_patch_to_update(tasks)
        tasks = self._dedupe_tasks(tasks)
        tasks = await self._semantic_dedupe_with_critical_ai(tasks)
        tasks = self._collapse_put_patch_to_update(tasks)
        tasks = self._dedupe_tasks(tasks)

        return tasks

    @staticmethod
    def _flatten_feature_items(features: list[CanonicalizationFeatureDTO], attr: str) -> list[CanonicalizationItemDTO]:
        flattened: list[CanonicalizationItemDTO] = []
        for feature in features:
            flattened.extend(getattr(feature, attr))
        return flattened

    def _compute_minimum_task_target(self, canonicalization: CanonicalizationResultDTO) -> int:
        feature_count = len(canonicalization.features)

        feature_apis = self._flatten_feature_items(canonicalization.features, "apis")
        feature_database = self._flatten_feature_items(canonicalization.features, "database")

        api_count = len(canonicalization.apis) + len(feature_apis)
        db_schema_count = len(canonicalization.database) + len(feature_database)

        # Conservative dynamic floor to avoid under-generation on rich inputs.
        dynamic_floor = (feature_count * 3) + (api_count * 2) + (db_schema_count * 2)
        return max(12, dynamic_floor)

    @staticmethod
    def _has_any_signal(canonicalization: CanonicalizationResultDTO) -> bool:
        return bool(
            canonicalization.features
            or canonicalization.tasks
            or canonicalization.apis
            or canonicalization.database
        )

    def _build_primary_context(self, canonicalization: CanonicalizationResultDTO) -> dict:
        all_tasks = self._all_tasks(canonicalization)
        all_apis = self._all_apis(canonicalization)
        all_db = self._all_database(canonicalization)

        planning_tasks = [
            item for item in all_tasks
            if item.source_file_type == SourceFileType.PLANNING
        ]
        design_items = [
            *[item for item in all_apis if item.source_file_type == SourceFileType.DESIGN],
            *[item for item in all_db if item.source_file_type == SourceFileType.DESIGN],
        ]
        requirement_features = [
            item for item in canonicalization.features
            if item.source_file_type == SourceFileType.REQUIREMENT
        ]

        if planning_tasks:
            return {
                "primary_signal_type": "tasks",
                "mode": "planning",
                "primary_items": self._sort_by_origin(planning_tasks),
            }

        if design_items:
            return {
                "primary_signal_type": "design",
                "mode": "design",
                "primary_items": self._sort_by_origin(design_items),
            }

        if requirement_features:
            return {
                "primary_signal_type": "none",
                "mode": "feature_to_tech_design",
                "primary_items": [],
            }

        return {
            "primary_signal_type": "none",
            "mode": "empty",
            "primary_items": [],
        }

    @staticmethod
    def _sort_by_origin(items: list[CanonicalizationItemDTO]) -> list[CanonicalizationItemDTO]:
        return sorted(
            items,
            key=lambda item: (
                TASK_GENERATION_ORIGIN_RANK.get(item.signal_origin, 99),
                TASK_GENERATION_SOURCE_RANK.get(item.source_file_type, 99),
                item.title.casefold(),
            ),
        )

    def _generate_deterministic_tasks(
        self,
        canonicalization: CanonicalizationResultDTO,
        primary_context: dict,
    ) -> list[AISprintGenerationResultTaskDTO]:
        mode = str(primary_context.get("mode") or "")

        if mode == "planning":
            return self._build_planning_mode_tasks(canonicalization)

        if mode == "design":
            return self._build_design_mode_tasks(canonicalization)

        if mode == "feature_to_tech_design":
            return self._build_feature_fallback_tasks(canonicalization)

        return []

    def _build_planning_mode_tasks(self, canonicalization: CanonicalizationResultDTO) -> list[AISprintGenerationResultTaskDTO]:
        all_tasks = self._all_tasks(canonicalization)

        # Preserve user intent tasks exactly when planning+explicit.
        retained = [
            task for task in all_tasks
            if task.source_file_type == SourceFileType.PLANNING and task.signal_origin == SignalOrigin.EXPLICIT
        ]
        extras = [
            task for task in all_tasks
            if not (task.source_file_type == SourceFileType.PLANNING and task.signal_origin == SignalOrigin.EXPLICIT)
        ]

        deterministic: list[AISprintGenerationResultTaskDTO] = [
            self._from_canonical_task(task)
            for task in [*retained, *extras]
        ]

        # Optional bounded inference for uncovered API/DB in planning mode.
        inferred_candidates = [
            *self._build_api_tasks(self._all_apis(canonicalization), include_qc=False),
            *self._build_db_tasks(self._all_database(canonicalization)),
        ]
        infer_cap = max(1, int(math.ceil(max(len(deterministic), 1) * 0.3)))
        deterministic.extend(inferred_candidates[:infer_cap])

        return deterministic

    def _build_design_mode_tasks(self, canonicalization: CanonicalizationResultDTO) -> list[AISprintGenerationResultTaskDTO]:
        apis = self._all_apis(canonicalization)
        db_items = self._all_database(canonicalization)
        return [
            *self._build_api_tasks(apis, include_qc=True),
            *self._build_db_tasks(db_items),
        ]

    def _build_feature_fallback_tasks(self, canonicalization: CanonicalizationResultDTO) -> list[AISprintGenerationResultTaskDTO]:
        tasks: list[AISprintGenerationResultTaskDTO] = []

        for feature in canonicalization.features:
            title = feature.title.strip()
            if not title:
                continue

            tasks.append(
                self._build_task(
                    name=f"Define technical design for {title}",
                    description=f"Define technical architecture, boundaries, and acceptance criteria for {title}",
                    source_file_name=feature.source_file_name,
                    source_file_type=feature.source_file_type,
                    signal_origin=feature.signal_origin,
                    priority="MEDIUM",
                    story_point=3,
                )
            )
            tasks.append(
                self._build_task(
                    name=f"Design API contract for {title}",
                    description=f"Design request/response contracts and validation strategy for {title}",
                    source_file_name=feature.source_file_name,
                    source_file_type=feature.source_file_type,
                    signal_origin=feature.signal_origin,
                    priority="MEDIUM",
                    story_point=3,
                )
            )

        return tasks

    def _build_api_tasks(
        self,
        apis: list[CanonicalizationItemDTO],
        include_qc: bool,
    ) -> list[AISprintGenerationResultTaskDTO]:
        tasks: list[AISprintGenerationResultTaskDTO] = []

        for api in apis:
            api_title = api.title.strip()
            if not api_title:
                continue

            tasks.append(
                self._build_task(
                    name=f"Implement {api_title}",
                    description=f"Implement endpoint contract, validation, authorization, and handler logic for {api_title}",
                    source_file_name=api.source_file_name,
                    source_file_type=api.source_file_type,
                    signal_origin=api.signal_origin,
                    priority="HIGH",
                    story_point=5,
                )
            )

            if include_qc:
                tasks.append(
                    self._build_task(
                        name=f"Verify {api_title} behavior",
                        description=f"Write and execute API tests for {api_title}, including success, validation, and error-path checks",
                        source_file_name=api.source_file_name,
                        source_file_type=api.source_file_type,
                        signal_origin=api.signal_origin,
                        priority="MEDIUM",
                        story_point=3,
                    )
                )

        return tasks

    def _build_db_tasks(self, db_items: list[CanonicalizationItemDTO]) -> list[AISprintGenerationResultTaskDTO]:
        tasks: list[AISprintGenerationResultTaskDTO] = []

        for db_item in db_items:
            title = db_item.title.strip()
            if not title:
                continue

            tasks.append(
                self._build_task(
                    name=f"Design {title} schema",
                    description=f"Design schema structure, indexes, and constraints for {title}",
                    source_file_name=db_item.source_file_name,
                    source_file_type=db_item.source_file_type,
                    signal_origin=db_item.signal_origin,
                    priority="HIGH",
                    story_point=3,
                )
            )
            tasks.append(
                self._build_task(
                    name=f"Create migration for {title}",
                    description=f"Create and validate migration scripts for {title} schema evolution",
                    source_file_name=db_item.source_file_name,
                    source_file_type=db_item.source_file_type,
                    signal_origin=db_item.signal_origin,
                    priority="MEDIUM",
                    story_point=2,
                )
            )

        return tasks

    def _validate_coverage(
        self,
        primary_context: dict,
        tasks: list[AISprintGenerationResultTaskDTO],
    ) -> tuple[list[CoverageIssueDTO], CoverageSummaryDTO]:
        issues: list[CoverageIssueDTO] = []
        primary_items: list[CanonicalizationItemDTO] = list(primary_context.get("primary_items") or [])
        mode = str(primary_context.get("mode") or "")

        covered_count = 0
        for item in primary_items:
            matched = self._find_related_task(item, tasks)
            if matched is None:
                issues.append(
                    CoverageIssueDTO(
                        issue_id=f"cov-missing-{item.id}",
                        level="ERROR",
                        issue_type="MISSING_COVERAGE",
                        signal_ref={"id": item.id, "type": item.type, "title": item.title},
                        task_ref=None,
                        message=f"Missing coverage for primary item: {item.title}",
                    )
                )
                continue

            covered_count += 1
            if (
                matched.source_file_name != item.source_file_name
                or matched.source_file_type != item.source_file_type
                or matched.signal_origin != item.signal_origin
            ):
                issues.append(
                    CoverageIssueDTO(
                        issue_id=f"cov-source-{item.id}",
                        level="ERROR",
                        issue_type="SOURCE_MISMATCH",
                        signal_ref={"id": item.id, "type": item.type, "title": item.title},
                        task_ref={"name": matched.name},
                        message="Task source lineage does not match covered primary signal",
                    )
                )

        duplicate_intent_count = 0
        seen_intents: dict[str, int] = {}
        for task in tasks:
            intent = self._task_intent_key(task.name)
            if not intent:
                continue
            seen_intents[intent] = seen_intents.get(intent, 0) + 1
        for intent_key, count in seen_intents.items():
            if count < 2:
                continue
            duplicate_intent_count += 1
            issues.append(
                CoverageIssueDTO(
                    issue_id=f"cov-dup-{intent_key[:24]}",
                    level="ERROR",
                    issue_type="DUPLICATE_INTENT",
                    signal_ref=None,
                    task_ref={"intent": intent_key, "count": count},
                    message=f"Duplicate task intent detected: {intent_key}",
                )
            )

        weak_task_count = 0
        for idx, task in enumerate(tasks, start=1):
            if self._is_weak_task(task):
                weak_task_count += 1
                issues.append(
                    CoverageIssueDTO(
                        issue_id=f"cov-weak-{idx}",
                        level="WARNING",
                        issue_type="WEAK_TASK",
                        signal_ref=None,
                        task_ref={"name": task.name, "index": idx},
                        message="Task name/description is too weak for deterministic coverage",
                    )
                )

        if mode == "design":
            api_missing_qc = self._find_missing_design_qc(tasks)
            for api_title in api_missing_qc:
                issues.append(
                    CoverageIssueDTO(
                        issue_id=f"cov-qc-{self._normalize_text(api_title)[:24]}",
                        level="ERROR",
                        issue_type="MISSING_COVERAGE",
                        signal_ref={"type": "api", "title": api_title},
                        task_ref=None,
                        message=f"Missing QC task for API: {api_title}",
                    )
                )

        error_count = sum(1 for issue in issues if issue.level == "ERROR")
        warning_count = sum(1 for issue in issues if issue.level == "WARNING")
        primary_total = len(primary_items)
        coverage_ratio = float(covered_count / primary_total) if primary_total else 1.0

        summary = CoverageSummaryDTO(
            primary_total=primary_total,
            covered_total=covered_count,
            primary_coverage_ratio=coverage_ratio,
            error_count=error_count,
            warning_count=warning_count,
            duplicate_intent_count=duplicate_intent_count,
            weak_task_count=weak_task_count,
        )
        return issues, summary

    def _repair_from_issues(
        self,
        primary_context: dict,
        issues: list[CoverageIssueDTO],
    ) -> list[AISprintGenerationResultTaskDTO]:
        mode = str(primary_context.get("mode") or "")
        primary_items = {
            item.id: item
            for item in (primary_context.get("primary_items") or [])
            if isinstance(item, CanonicalizationItemDTO)
        }

        repairs: list[AISprintGenerationResultTaskDTO] = []
        for issue in issues:
            if issue.level != "ERROR" or issue.issue_type != "MISSING_COVERAGE":
                continue

            signal_ref = issue.signal_ref if isinstance(issue.signal_ref, dict) else {}
            item_id = str(signal_ref.get("id") or "").strip()
            if item_id and item_id in primary_items:
                repairs.append(self._from_canonical_task(primary_items[item_id]))
                continue

            if mode == "design" and str(signal_ref.get("type") or "") == "api":
                api_title = str(signal_ref.get("title") or "").strip()
                if api_title:
                    repairs.append(
                        self._build_task(
                            name=f"Verify {api_title} behavior",
                            description=f"Write and execute API tests for {api_title}, including success and failure paths",
                            source_file_name="unknown",
                            source_file_type=SourceFileType.DESIGN,
                            signal_origin=SignalOrigin.DERIVED,
                            priority="MEDIUM",
                            story_point=2,
                        )
                    )

        return repairs

    def _find_related_task(
        self,
        item: CanonicalizationItemDTO,
        tasks: list[AISprintGenerationResultTaskDTO],
    ) -> AISprintGenerationResultTaskDTO | None:
        target = self._normalize_text(item.title)
        target_tokens = self._tokenize(item.title)
        best: tuple[float, AISprintGenerationResultTaskDTO] | None = None

        for task in tasks:
            candidate = self._normalize_text(f"{task.name} {task.description}")
            candidate_tokens = self._tokenize(candidate)

            if target and target in candidate:
                score = 1.0
            else:
                score = self._token_overlap(target_tokens, candidate_tokens)

            if best is None or score > best[0]:
                best = (score, task)

        if best is None:
            return None
        return best[1] if best[0] >= 0.55 else None

    @staticmethod
    def _find_missing_design_qc(tasks: list[AISprintGenerationResultTaskDTO]) -> list[str]:
        implemented_apis: set[str] = set()
        qc_apis: set[str] = set()

        for task in tasks:
            name = task.name.strip()
            lowered = name.casefold()
            if lowered.startswith("implement "):
                implemented_apis.add(name[len("Implement "):].strip())
            if lowered.startswith("verify ") or " test" in lowered or "testing" in lowered:
                api = re.sub(TASK_GENERATION_VERIFY_PREFIX_REGEX, "", name, flags=re.IGNORECASE).strip()
                api = re.sub(TASK_GENERATION_BEHAVIOR_SUFFIX_REGEX, "", api, flags=re.IGNORECASE).strip()
                if api:
                    qc_apis.add(api)

        return sorted([api for api in implemented_apis if api not in qc_apis])

    def _task_intent_key(self, name: str) -> str:
        tokens = [t for t in self._tokenize(name) if t not in TASK_GENERATION_STOPWORDS]
        if not tokens:
            return ""
        if tokens[0] in TASK_GENERATION_TASK_VERBS:
            tokens = tokens[:1] + sorted(tokens[1:])
        else:
            tokens = sorted(tokens)
        return " ".join(tokens)

    def _is_weak_task(self, task: AISprintGenerationResultTaskDTO) -> bool:
        name = (task.name or "").strip()
        desc = (task.description or "").strip()

        if len(name) < 10:
            return True
        name_tokens = self._tokenize(name)
        if not name_tokens:
            return True

        first = next(iter(name_tokens), "")
        if first in TASK_GENERATION_TASK_VERBS and len(name_tokens) <= 1:
            return True

        if all(token in TASK_GENERATION_GENERIC_WORDS for token in name_tokens):
            return True

        return len(desc) < 20

    @staticmethod
    def _normalize_text(value: str) -> str:
        cleaned = re.sub(TASK_GENERATION_TEXT_SANITIZE_REGEX, " ", (value or "").casefold(), flags=re.UNICODE)
        return re.sub(TASK_GENERATION_WHITESPACE_REGEX, " ", cleaned).strip()

    def _tokenize(self, value: str) -> set[str]:
        text = self._normalize_text(value)
        tokens = set(re.findall(TASK_GENERATION_TOKEN_REGEX, text, flags=re.UNICODE))
        return {token for token in tokens if len(token) > 1}

    @staticmethod
    def _token_overlap(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left.intersection(right))
        union = len(left.union(right))
        return float(intersection / union) if union else 0.0

    @staticmethod
    def _build_task(
        name: str,
        description: str,
        source_file_name: str,
        source_file_type: SourceFileType,
        signal_origin: SignalOrigin,
        priority: str | None = None,
        story_point: int | None = None,
        due_date: str | None = None,
    ) -> AISprintGenerationResultTaskDTO:
        return AISprintGenerationResultTaskDTO(
            name=name,
            description=description,
            source_file_name=source_file_name,
            source_file_type=source_file_type,
            signal_origin=signal_origin,
            priority=priority,
            story_point=story_point,
            due_date=due_date,
        )

    def _from_canonical_task(self, item: CanonicalizationItemDTO) -> AISprintGenerationResultTaskDTO:
        title = (item.title or "").strip()
        description = (item.description or "").strip() or f"Implement {title}"
        return self._build_task(
            name=title,
            description=description,
            source_file_name=item.source_file_name,
            source_file_type=item.source_file_type,
            signal_origin=item.signal_origin,
        )

    @staticmethod
    def _all_tasks(canonicalization: CanonicalizationResultDTO) -> list[CanonicalizationItemDTO]:
        feature_tasks = TaskGenerationPipeline._flatten_feature_items(canonicalization.features, "tasks")
        return [*canonicalization.tasks, *feature_tasks]

    @staticmethod
    def _all_apis(canonicalization: CanonicalizationResultDTO) -> list[CanonicalizationItemDTO]:
        feature_apis = TaskGenerationPipeline._flatten_feature_items(canonicalization.features, "apis")
        return [*canonicalization.apis, *feature_apis]

    @staticmethod
    def _all_database(canonicalization: CanonicalizationResultDTO) -> list[CanonicalizationItemDTO]:
        feature_db = TaskGenerationPipeline._flatten_feature_items(canonicalization.features, "database")
        return [*canonicalization.database, *feature_db]

    @staticmethod
    def _dedupe_tasks(tasks: list[AISprintGenerationResultTaskDTO]) -> list[AISprintGenerationResultTaskDTO]:
        unique: list[AISprintGenerationResultTaskDTO] = []
        seen: set[str] = set()

        for task in tasks:
            key = re.sub(TASK_GENERATION_WHITESPACE_REGEX, " ", task.name.strip()).casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(task)

        return unique

    def _collapse_put_patch_to_update(
        self,
        tasks: list[AISprintGenerationResultTaskDTO],
    ) -> list[AISprintGenerationResultTaskDTO]:
        grouped: dict[tuple[str, str, bool], list[AISprintGenerationResultTaskDTO]] = {}
        passthrough: list[AISprintGenerationResultTaskDTO] = []

        for task in tasks:
            parsed = self._parse_api_task_name(task.name)
            if parsed is None:
                passthrough.append(task)
                continue

            action, method, endpoint, is_behavior = parsed
            if method not in {"PUT", "PATCH"}:
                passthrough.append(task)
                continue

            grouped.setdefault((action, endpoint, is_behavior), []).append(task)

        collapsed: list[AISprintGenerationResultTaskDTO] = list(passthrough)
        for (action, endpoint, is_behavior), bucket in grouped.items():
            methods = {
                (self._parse_api_task_name(task.name) or ("", "", "", False))[1]
                for task in bucket
            }

            if not ({"PUT", "PATCH"}.issubset(methods)):
                collapsed.extend(bucket)
                continue

            selected = self._select_preferred_task(bucket)
            selected.name = self._format_api_task_name(action, "UPDATE", endpoint, is_behavior)
            selected.description = self._rewrite_put_patch_description_to_update(selected.description, endpoint)
            collapsed.append(selected)

        return collapsed

    async def _semantic_dedupe_with_critical_ai(
        self,
        tasks: list[AISprintGenerationResultTaskDTO],
    ) -> list[AISprintGenerationResultTaskDTO]:
        if not TASK_SEMANTIC_DEDUP_ENABLED or len(tasks) < 2:
            return tasks

        prompt = self._build_semantic_dedup_prompt()
        payload_file = await self.llm.upload_file(
            object_key="task_generation/semantic_dedup_input.json" + timestamp_suffix(),
            content=json.dumps({"tasks": [task.model_dump() for task in tasks]}, ensure_ascii=False, indent=2).encode("utf-8"),
            mime="application/json",
        )
        for attempt in range(1, TASK_SEMANTIC_DEDUP_MAX_TRY + 1):
            try:
                response_text = await self.llm.generate(
                    prompt=prompt,
                    model=LLMModel.GEMINI_2_5_FLASH,
                    afc_enabled=False,
                    files=[payload_file],
                    max_output_tokens=20000,
                    timeout_seconds=90.0,
                    temperature=0.1,
                    top_p=0.9,
                    top_k=40,
                )
                parsed_payload = self._parse_llm_json(response_text)
                parsed_items = self._extract_tasks(parsed_payload)
                candidate = self._normalize_tasks(parsed_items)
                if not self._is_semantic_dedup_output_safe(tasks, candidate):
                    continue
                return candidate
            except Exception:
                logging.exception(
                    "critical semantic dedup failed | attempt=%d/%d",
                    attempt,
                    TASK_SEMANTIC_DEDUP_MAX_TRY,
                )

        return tasks

    def _build_semantic_dedup_prompt(self) -> str:
        return (
            "You are Critical AI for strict task semantic deduplication.\n"
            "Input is provided as an attached JSON file with schema: {\"tasks\": [...]}.\n"
            "Rules:\n"
            "1) Remove semantic duplicates only; keep all unique work.\n"
            "2) Never merge different endpoint paths.\n"
            "3) Never merge different HTTP methods, except PUT/PATCH same endpoint+action => UPDATE.\n"
            "4) Keep Implement and Verify intents separate.\n"
            "5) Preserve source_file_name, source_file_type, signal_origin from chosen item.\n"
            "Output only valid JSON with this schema: {\"tasks\": [ ...task objects... ]}."
        )

    def _is_semantic_dedup_output_safe(
        self,
        original: list[AISprintGenerationResultTaskDTO],
        candidate: list[AISprintGenerationResultTaskDTO],
    ) -> bool:
        if not candidate:
            return False
        if len(candidate) > len(original):
            return False

        original_api = self._expected_api_signature_set(original)
        candidate_api = self._expected_api_signature_set(candidate)
        if candidate_api != original_api:
            return False

        return True

    def _expected_api_signature_set(
        self,
        tasks: list[AISprintGenerationResultTaskDTO],
    ) -> set[tuple[str, str, str, bool]]:
        grouped: dict[tuple[str, str, bool], set[str]] = {}
        for task in tasks:
            parsed = self._parse_api_task_name(task.name)
            if parsed is None:
                continue
            action, method, endpoint, is_behavior = parsed
            grouped.setdefault((action, endpoint, is_behavior), set()).add(method)

        signatures: set[tuple[str, str, str, bool]] = set()
        for (action, endpoint, is_behavior), methods in grouped.items():
            normalized_methods = set(methods)
            if {"PUT", "PATCH"}.issubset(normalized_methods):
                normalized_methods.discard("PUT")
                normalized_methods.discard("PATCH")
                normalized_methods.add("UPDATE")
            for method in normalized_methods:
                signatures.add((action, method, endpoint, is_behavior))

        return signatures

    @classmethod
    def _parse_api_task_name(cls, name: str) -> tuple[str, str, str, bool] | None:
        match = cls._API_TASK_NAME_REGEX.match((name or "").strip())
        if not match:
            return None

        action = match.group(1).capitalize()
        method = match.group(2).upper()
        endpoint = match.group(3).strip().lower()
        endpoint = re.sub(TASK_GENERATION_ENDPOINT_SLASH_COLLAPSE_REGEX, "/", endpoint)
        is_behavior = bool(match.group(4))
        return action, method, endpoint, is_behavior

    @staticmethod
    def _format_api_task_name(action: str, method: str, endpoint: str, is_behavior: bool) -> str:
        if is_behavior:
            return f"{action} {method} {endpoint} behavior"
        return f"{action} {method} {endpoint}"

    def _select_preferred_task(
        self,
        bucket: list[AISprintGenerationResultTaskDTO],
    ) -> AISprintGenerationResultTaskDTO:
        def score(task: AISprintGenerationResultTaskDTO) -> tuple[int, int]:
            signal_score = 0
            if task.signal_origin == SignalOrigin.EXPLICIT:
                signal_score = 2
            elif task.signal_origin == SignalOrigin.DERIVED:
                signal_score = 1

            source_score = 0
            if task.source_file_type == SourceFileType.REQUIREMENT:
                source_score = 2
            elif task.source_file_type == SourceFileType.DESIGN:
                source_score = 1

            return signal_score, source_score

        return max(bucket, key=score)

    @staticmethod
    def _rewrite_put_patch_description_to_update(description: str, endpoint: str) -> str:
        text = str(description or "")
        endpoint_escaped = re.escape(endpoint)
        text = re.sub(
            rf"\b(PUT|PATCH)\s+{endpoint_escaped}\b",
            f"UPDATE {endpoint}",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(TASK_GENERATION_METHOD_REWRITE_REGEX, "UPDATE", text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _extract_tasks(payload: object) -> list[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("tasks"), list):
                return [item for item in payload["tasks"] if isinstance(item, dict)]
            if isinstance(payload.get("items"), list):
                return [item for item in payload["items"] if isinstance(item, dict)]
        return []

    def _normalize_tasks(self, raw_items: list[dict]) -> list[AISprintGenerationResultTaskDTO]:
        tasks: list[AISprintGenerationResultTaskDTO] = []
        for item in raw_items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue

            description = str(item.get("description") or "").strip()
            if not description:
                description = f"Implement {name}"

            priority = item.get("priority")
            if isinstance(priority, str):
                priority = priority.strip().upper()
            if priority not in {"LOW", "MEDIUM", "HIGH"}:
                priority = None

            story_point = item.get("story_point")
            if isinstance(story_point, str) and story_point.strip().isdigit():
                story_point = int(story_point.strip())
            if story_point not in {1, 2, 3, 5, 8}:
                story_point = None

            due_date = item.get("due_date")
            if isinstance(due_date, str):
                due_date = due_date.strip() or None
            else:
                due_date = None
            if due_date and not re.match(TASK_DUE_DATE_REGEX, due_date):
                due_date = None

            source_file_name = str(item.get("source_file_name") or "").strip() or "unknown"
            source_file_type = self._parse_source_file_type(item.get("source_file_type"))
            signal_origin = self._parse_signal_origin(item.get("signal_origin"))

            tasks.append(
                AISprintGenerationResultTaskDTO(
                    name=name,
                    description=description,
                    source_file_name=source_file_name,
                    source_file_type=source_file_type,
                    signal_origin=signal_origin,
                    priority=priority,
                    story_point=story_point,
                    due_date=due_date,
                )
            )

        return tasks

    @staticmethod
    def _parse_source_file_type(value: object) -> SourceFileType:
        raw = str(value or "").strip().lower()
        if raw == SourceFileType.DESIGN.value.lower():
            return SourceFileType.DESIGN
        if raw == SourceFileType.REQUIREMENT.value.lower():
            return SourceFileType.REQUIREMENT
        return SourceFileType.PLANNING

    @staticmethod
    def _parse_signal_origin(value: object) -> SignalOrigin:
        raw = str(value or "").strip().lower()
        if raw == SignalOrigin.DERIVED.value:
            return SignalOrigin.DERIVED
        if raw == SignalOrigin.INFERRED.value:
            return SignalOrigin.INFERRED
        return SignalOrigin.EXPLICIT

    @staticmethod
    def _parse_llm_json(response_text: str) -> object:
        decoder = json.JSONDecoder()

        # Prefer fenced JSON blocks first when available.
        fenced_blocks = re.findall(TASK_GENERATION_JSON_FENCE_REGEX, response_text, re.DOTALL)
        for block in fenced_blocks:
            parsed = TaskGenerationPipeline._decode_first_json_value(block, decoder)
            if parsed is not None:
                return parsed

        # Fallback: decode from full response text.
        parsed = TaskGenerationPipeline._decode_first_json_value(response_text, decoder)
        if parsed is not None:
            return parsed

        logging.error("task generation parse error | invalid JSON response")
        raise ValueError("LLM response is not valid JSON")

    @staticmethod
    def _decode_first_json_value(text: str, decoder: json.JSONDecoder) -> object | None:
        if not text:
            return None

        candidate_starts = [idx for idx, ch in enumerate(text) if ch in "[{"]
        for start in candidate_starts:
            try:
                parsed, _ = decoder.raw_decode(text, start)
                return parsed
            except json.JSONDecodeError:
                continue
        return None

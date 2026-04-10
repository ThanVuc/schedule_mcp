import json
import logging
import re

from application.dtos.sprint_generation_dto import (
    AISprintGenerationRequestedPayloadDTO,
    AISprintGenerationResultTaskDTO,
    CanonicalizationFeatureDTO,
    CanonicalizationItemDTO,
    CanonicalizationResultDTO,
)
from domain.prompt.task_generation_prompt import BuildTaskExpansionPrompt, BuildTaskGenerationPrompt
from infrastructure.base.const.infra_const import LLMAgentName
from infrastructure.base.llm.gemini_llm import LLMConnector


class TaskGenerationPipeline:
    def __init__(self, llm: LLMConnector):
        self.llm = llm

    async def generate_tasks(
        self,
        canonicalization: CanonicalizationResultDTO,
        payload: AISprintGenerationRequestedPayloadDTO,
    ) -> list[AISprintGenerationResultTaskDTO]:
        target_min_tasks = self._compute_minimum_task_target(canonicalization)

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
        tasks = self._dedupe_tasks(self._normalize_tasks(parsed_items))

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
        feature_user_flows = self._flatten_feature_items(canonicalization.features, "user_flows")
        feature_db_schemas = self._flatten_feature_items(canonicalization.features, "db_schemas")

        api_count = len(canonicalization.apis) + len(feature_apis)
        user_flow_count = len(canonicalization.user_flows) + len(feature_user_flows)
        db_schema_count = len(canonicalization.db_schemas) + len(feature_db_schemas)

        # Conservative dynamic floor to avoid under-generation on rich inputs.
        dynamic_floor = (feature_count * 3) + (api_count * 2) + (user_flow_count * 2) + (db_schema_count * 2)
        return max(12, dynamic_floor)

    @staticmethod
    def _dedupe_tasks(tasks: list[AISprintGenerationResultTaskDTO]) -> list[AISprintGenerationResultTaskDTO]:
        unique: list[AISprintGenerationResultTaskDTO] = []
        seen: set[str] = set()

        for task in tasks:
            key = re.sub(r"\s+", " ", task.name.strip()).casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(task)

        return unique

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
            if due_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
                due_date = None

            tasks.append(
                AISprintGenerationResultTaskDTO(
                    name=name,
                    description=description,
                    priority=priority,
                    story_point=story_point,
                    due_date=due_date,
                )
            )

        return tasks

    @staticmethod
    def _parse_llm_json(response_text: str) -> object:
        decoder = json.JSONDecoder()

        # Prefer fenced JSON blocks first when available.
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL)
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

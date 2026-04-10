import json
import logging
import re

from application.dtos.sprint_generation_dto import (
    AISprintGenerationRequestedPayloadDTO,
    AISprintGenerationResultTaskDTO,
    CanonicalizationResultDTO,
)
from domain.prompt.task_generation_prompt import BuildTaskGenerationPrompt
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
        prompt = BuildTaskGenerationPrompt(
            additional_context=payload.additional_context,
            sprint_name=payload.sprint.name,
            sprint_goal=payload.sprint.goal,
            sprint_start_date=payload.sprint.start_date,
            sprint_end_date=payload.sprint.end_date,
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
            max_output_tokens=4096,
        )

        parsed_items = self._extract_tasks(self._parse_llm_json(response_text))
        tasks = self._normalize_tasks(parsed_items)
        return tasks

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

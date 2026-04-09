import asyncio
import json
import os
import re

from aio_pika import logger
from application.dtos.common import FileDTO
from application.dtos.sprint_generation_dto import ClassificationResultDTO
from domain.prompt.classify_and_extract_prompt import BuildClassifyAndExtractPrompt
from infrastructure.base.const.infra_const import LLMAgentName
from infrastructure.container import InfrastructureContainer


class ClassifyAndExtractPipeline:
    _TYPE_BY_PREFIX = {
        "design": "Design",
        "planning": "Planning",
        "requirement": "Requirement",
    }

    def __init__(self, infra: InfrastructureContainer, max_concurrency: int = 5):
        self.storage = infra.get_storage()
        self.llm = infra.get_llm_connector()
        self._semaphore = asyncio.Semaphore(max_concurrency)
    
    async def classify_and_extract(self, file_dtos: list[FileDTO]) -> list[ClassificationResultDTO]:
        tasks = [self._classify_one(file_dto) for file_dto in file_dtos]
        return await asyncio.gather(*tasks)

    async def _classify_one(self, file_dto: FileDTO) -> ClassificationResultDTO:
        async with self._semaphore:
            prompt = BuildClassifyAndExtractPrompt()

            response_text = await self.llm.generate_for_agent(
                prompt=prompt,
                agent_name=LLMAgentName.EXTRACTION,
                afc_enabled=False,
                files=[file_dto],
                max_output_tokens=4096,
            )

            payload = self._parse_llm_json(response_text)
            payload["file_name"] = file_dto.name
            payload["type"] = self._resolve_type(file_dto.name, payload.get("type"))

            # For debugging: print to response to evidence folder
            evidence_path = f"z_evidence/classify_and_extract/{file_dto.name}.json"
            os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
            with open(evidence_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

            return ClassificationResultDTO.model_validate(payload)

    @classmethod
    def _resolve_type(cls, file_name: str, llm_type: str | None) -> str:
        prefix_type = cls._type_from_file_prefix(file_name)
        if prefix_type:
            return prefix_type

        if llm_type in cls._TYPE_BY_PREFIX.values():
            return llm_type

        return "Planning"

    @classmethod
    def _type_from_file_prefix(cls, file_name: str) -> str | None:
        base_name = os.path.basename(file_name or "")
        stem_name = os.path.splitext(base_name)[0].strip().lower()

        # Match only agreed FE prefixes: design*, planning*, requirement*.
        for prefix, mapped_type in cls._TYPE_BY_PREFIX.items():
            if stem_name == prefix:
                return mapped_type
            if stem_name.startswith(prefix):
                return mapped_type
            if stem_name.startswith(f"{prefix}-") or stem_name.startswith(f"{prefix}_") or stem_name.startswith(f"{prefix} "):
                return mapped_type

        return None

    @staticmethod
    def _parse_llm_json(response_text: str) -> dict:
        # First, handle common fenced JSON outputs.
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response_text, re.DOTALL)
        candidate = fenced_match.group(1) if fenced_match else response_text

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Fallback: try to parse the largest JSON object substring.
            first_brace = candidate.find("{")
            last_brace = candidate.rfind("}")
            if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
                logger.error("Classification parse error | invalid JSON response=%s", response_text)
                raise ValueError("LLM response is not valid JSON")

            json_slice = candidate[first_brace:last_brace + 1]
            try:
                return json.loads(json_slice)
            except json.JSONDecodeError as exc:
                logger.error("Classification parse error | invalid JSON slice=%s", json_slice)
                raise ValueError("LLM response JSON parse failed") from exc
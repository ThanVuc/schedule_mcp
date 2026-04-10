
import json
import logging
import re

from application.dtos.sprint_generation_dto import (
    MergedItemDTO,
    NormalizationResultDTO,
    NormalizationSourceDTO,
    NormalizedItemDTO,
    ReconciliationResultDTO,
)
from domain.prompt.reconciliation_prompt import BuildReconciliationPrompt
from infrastructure.base.const.infra_const import LLMAgentName, LLMModel
from infrastructure.base.llm.gemini_llm import LLMConnector


class ReconciliationPipeline:
    _VALID_TYPES = {"feature", "task", "user_flow", "api", "db_schema"}

    def __init__(self, llm: LLMConnector, max_concurrency: int = 5):
        self.llm = llm
        self._max_concurrency = max_concurrency
    
    async def reconcile(
        self,
        data: NormalizationResultDTO,
    ) -> ReconciliationResultDTO:
        collection_by_type: dict[str, list[NormalizedItemDTO]] = {
            "feature": data.features,
            "task": data.tasks,
            "user_flow": data.user_flows,
            "api": data.apis,
            "db_schema": data.db_schemas,
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
        user_flows = self._build_collection_result(
            item_type="user_flow",
            items=data.user_flows,
            cluster_map=cluster_map_by_type["user_flow"],
            merged_by_key=merged_by_key,
        )
        apis = self._build_collection_result(
            item_type="api",
            items=data.apis,
            cluster_map=cluster_map_by_type["api"],
            merged_by_key=merged_by_key,
        )
        db_schemas = self._build_collection_result(
            item_type="db_schema",
            items=data.db_schemas,
            cluster_map=cluster_map_by_type["db_schema"],
            merged_by_key=merged_by_key,
        )

        result = ReconciliationResultDTO(
            features=features,
            tasks=tasks,
            user_flows=user_flows,
            apis=apis,
            db_schemas=db_schemas,
        )
        return result

    @staticmethod
    def _build_cluster_map(items: list[NormalizedItemDTO]) -> dict[str, list[NormalizedItemDTO]]:
        cluster_map: dict[str, list[NormalizedItemDTO]] = {}
        for item in items:
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
                if len(items) < 2:
                    continue
                payload.append(
                    {
                        "type": item_type,
                        "cluster_id": cluster_id,
                        "items": [
                            {
                                "title": item.content.title,
                                "description": item.content.description,
                                "source": {
                                    "file_name": item.source.file_name,
                                    "file_type": item.source.type,
                                },
                            }
                            for item in items
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

        prompt = BuildReconciliationPrompt()
        uploaded_file = await self.llm.upload_file(
            object_key="reconciliation/batch_clusters.json",
            content=json.dumps({"clusters": ai_clusters_payload}, ensure_ascii=False, indent=2).encode("utf-8"),
            mime="application/json",
        )

        try:
            response_text = await self.llm.generate_for_agent(
                prompt=prompt,
                agent_name=LLMModel.GEMINI_3_0_FLASH,
                afc_enabled=False,
                files=[uploaded_file],
                max_output_tokens=4096,
            )
            llm_payload = self._parse_llm_json(response_text)
            merged_items = self._extract_merged_items(llm_payload)
        except Exception:
            logging.exception(
                "reconciliation batch merge failed - fallback to flash lite | clusters=%d",
                len(ai_clusters_payload),
            )
            try:
                response_text = await self.llm.generate_for_agent(
                    prompt=prompt,
                    agent_name=LLMModel.GEMINI_3_1_FLASH_LITE,
                    afc_enabled=False,
                    files=[uploaded_file],
                    max_output_tokens=4096,
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
        
        if len(merged_by_key) < len(ai_clusters_payload) * 0.5:
            logging.warning(
                "Merged items from LLM are less than 50%% of input clusters - possible LLM failure, fallback to heuristic | merged=%d, input_clusters=%d",
                len(merged_by_key),
                len(ai_clusters_payload),
            )
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
            cluster_id = item.cluster_id
            if not cluster_id:
                result.append(self._to_single_item(item_type, item))
                continue

            cluster_items = cluster_map.get(cluster_id, [])
            if len(cluster_items) < 2:
                if cluster_id in emitted_clusters:
                    continue
                result.append(self._to_single_item(item_type, cluster_items[0] if cluster_items else item))
                emitted_clusters.add(cluster_id)
                continue

            if cluster_id in emitted_clusters:
                continue

            merged_item = merged_by_key.get((item_type, cluster_id))
            if merged_item is None:
                merged_item = self._fallback_merge(item_type, cluster_id, cluster_items)
            result.append(merged_item)
            emitted_clusters.add(cluster_id)

        return result

    def _to_merged_item_from_llm(
        self,
        expected_type: str,
        cluster_id: str,
        llm_payload: dict,
        fallback_items: list[NormalizedItemDTO],
    ) -> MergedItemDTO:
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

        aliases_raw = llm_payload.get("aliases") or []
        aliases = self._normalize_aliases(aliases_raw)

        sources_raw = llm_payload.get("source")
        if not isinstance(sources_raw, list):
            sources_raw = llm_payload.get("sources")
        sources = self._normalize_sources(sources_raw)

        if not title:
            return self._fallback_merge(expected_type, cluster_id, fallback_items)

        if not sources:
            sources = self._collect_sources(fallback_items)

        return MergedItemDTO(
            id=f"{expected_type}:{cluster_id}",
            type=resolved_type,
            title=title,
            description=description,
            aliases=aliases,
            sources=sources,
            cluster_id=cluster_id,
        )

    def _fallback_merge(
        self,
        item_type: str,
        cluster_id: str,
        items: list[NormalizedItemDTO],
    ) -> MergedItemDTO:
        representative = max(
            items,
            key=lambda item: len(item.content.title or "") + len(item.content.description or ""),
        )
        aliases = self._normalize_aliases([item.content.title for item in items])
        if representative.content.title in aliases:
            aliases.remove(representative.content.title)

        return MergedItemDTO(
            id=f"{item_type}:{cluster_id}",
            type=item_type,
            title=representative.content.title,
            description=representative.content.description,
            aliases=aliases,
            sources=self._collect_sources(items),
            cluster_id=cluster_id,
        )

    def _to_single_item(self, item_type: str, item: NormalizedItemDTO) -> MergedItemDTO:
        return MergedItemDTO(
            id=item.id,
            type=item_type,
            title=item.content.title,
            description=item.content.description,
            aliases=[],
            sources=[
                NormalizationSourceDTO(
                    file_name=item.source.file_name,
                    type=item.source.type,
                )
            ],
            cluster_id=item.cluster_id,
        )

    @staticmethod
    def _normalize_aliases(raw_aliases: object) -> list[str]:
        if not isinstance(raw_aliases, list):
            return []

        seen: set[str] = set()
        aliases: list[str] = []
        for alias in raw_aliases:
            if not isinstance(alias, str):
                continue
            cleaned = alias.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(cleaned)
        return aliases

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
            key = (item.source.file_name, item.source.type)
            unique[key] = NormalizationSourceDTO(
                file_name=item.source.file_name,
                type=item.source.type,
            )

        return sorted(unique.values(), key=lambda s: s.file_name.lower())

    @staticmethod
    def _parse_llm_json(response_text: str) -> dict:
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", response_text, re.DOTALL)
        candidate = fenced_match.group(1) if fenced_match else response_text

        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return {"merged_items": parsed}
            if not isinstance(parsed, dict):
                raise ValueError("LLM response must be a JSON object")
            return parsed
        except json.JSONDecodeError:
            first_brace = candidate.find("{")
            last_brace = candidate.rfind("}")
            first_bracket = candidate.find("[")
            last_bracket = candidate.rfind("]")

            json_slice = None
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                json_slice = candidate[first_brace:last_brace + 1]
            elif first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                json_slice = candidate[first_bracket:last_bracket + 1]

            if json_slice is None:
                raise ValueError("LLM response is not valid JSON")

            parsed = json.loads(json_slice)
            if isinstance(parsed, list):
                return {"merged_items": parsed}
            if not isinstance(parsed, dict):
                raise ValueError("LLM response must be a JSON object")
            return parsed



import re

from application.dtos.sprint_generation_dto import (
    CanonicalizationFeatureDTO,
    CanonicalizationItemDTO,
    CanonicalizationResultDTO,
    MergedItemDTO,
    ReconciliationResultDTO,
)
from infrastructure.base.embedder.embedder import Embedder


class CanonicalizationPipeline:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def canonicalize(
        self,
        items: ReconciliationResultDTO,
    ) -> CanonicalizationResultDTO:
        features = [self._to_feature(item) for item in items.features]
        feature_signals = [self._build_feature_signal(feature) for feature in features]

        orphan_tasks: list[CanonicalizationItemDTO] = []
        orphan_user_flows: list[CanonicalizationItemDTO] = []
        orphan_apis: list[CanonicalizationItemDTO] = []
        orphan_db_schemas: list[CanonicalizationItemDTO] = []

        task_feature_index: dict[str, int] = {}

        for task in items.tasks:
            task_item = self._to_item(task)
            feature_idx = self._find_best_feature_index(task, feature_signals)
            if feature_idx is None:
                orphan_tasks.append(task_item)
                continue

            features[feature_idx].tasks.append(task_item)
            task_feature_index[task.id] = feature_idx

        for flow in items.user_flows:
            flow_item = self._to_item(flow)
            feature_idx = self._find_best_feature_index(flow, feature_signals)
            if feature_idx is None:
                orphan_user_flows.append(flow_item)
                continue

            features[feature_idx].user_flows.append(flow_item)

        for api in items.apis:
            api_item = self._to_item(api)
            feature_idx = self._find_best_feature_index(api, feature_signals)
            if feature_idx is None:
                feature_idx = self._find_feature_index_via_task(api, items.tasks, task_feature_index)

            if feature_idx is None:
                orphan_apis.append(api_item)
                continue

            features[feature_idx].apis.append(api_item)

        for db_schema in items.db_schemas:
            db_item = self._to_item(db_schema)
            feature_idx = self._find_best_feature_index(db_schema, feature_signals)
            if feature_idx is None:
                feature_idx = self._find_feature_index_via_task(db_schema, items.tasks, task_feature_index)

            if feature_idx is None:
                orphan_db_schemas.append(db_item)
                continue

            features[feature_idx].db_schemas.append(db_item)

        result = CanonicalizationResultDTO(
            features=features,
            tasks=orphan_tasks,
            user_flows=orphan_user_flows,
            apis=orphan_apis,
            db_schemas=orphan_db_schemas,
        )
        return result

    def _find_feature_index_via_task(
        self,
        item: MergedItemDTO,
        tasks: list[MergedItemDTO],
        task_feature_index: dict[str, int],
    ) -> int | None:
        task_scores: list[tuple[int, float]] = []
        for idx, task in enumerate(tasks):
            score = self._link_score(item, task)
            if score <= 0.0:
                continue
            task_scores.append((idx, score))

        if not task_scores:
            return None

        best_task_idx, best_score = max(task_scores, key=lambda pair: pair[1])
        if best_score < 0.5:
            return None

        task_id = tasks[best_task_idx].id
        return task_feature_index.get(task_id)

    def _find_best_feature_index(
        self,
        item: MergedItemDTO,
        feature_signals: list[dict],
    ) -> int | None:
        if not feature_signals:
            return None

        exact_candidates: list[int] = []
        for idx, signal in enumerate(feature_signals):
            if self._is_exact_or_alias_match(item, signal):
                exact_candidates.append(idx)

        if len(exact_candidates) == 1:
            return exact_candidates[0]
        if len(exact_candidates) > 1:
            scored = [
                (idx, self._keyword_overlap(item, feature_signals[idx]))
                for idx in exact_candidates
            ]
            best_idx, best_score = max(scored, key=lambda pair: pair[1])
            return best_idx if best_score > 0 else exact_candidates[0]

        overlap_scores = [
            (idx, self._keyword_overlap(item, signal))
            for idx, signal in enumerate(feature_signals)
        ]
        best_idx, best_overlap = max(overlap_scores, key=lambda pair: pair[1])
        if best_overlap >= 0.2:
            return best_idx

        # Optional embedding fallback for ambiguous/no-overlap matches.
        return self._embedding_best_feature(item, feature_signals)

    def _embedding_best_feature(self, item: MergedItemDTO, feature_signals: list[dict]) -> int | None:
        if not feature_signals:
            return None

        item_text = self._compose_text(item.title, item.description)
        item_embedding = self.embedder.embed(item_text)

        feature_embeddings = self.embedder.embed_batch(
            [signal["embedding_text"] for signal in feature_signals]
        )
        scored = [
            (idx, self.embedder.cosine_similarity(item_embedding, feature_embedding))
            for idx, feature_embedding in enumerate(feature_embeddings)
        ]
        best_idx, best_score = max(scored, key=lambda pair: pair[1])
        if best_score < 0.5:
            return None
        return best_idx

    @staticmethod
    def _is_exact_or_alias_match(item: MergedItemDTO, signal: dict) -> bool:
        title_norm = CanonicalizationPipeline._normalize_phrase(item.title)
        if not title_norm:
            return False

        feature_titles: set[str] = signal["title_aliases"]
        if title_norm in feature_titles:
            return True

        for candidate in feature_titles:
            if title_norm in candidate or candidate in title_norm:
                return True

        return False

    @staticmethod
    def _keyword_overlap(item: MergedItemDTO, signal: dict) -> float:
        item_tokens = CanonicalizationPipeline._tokenize(
            CanonicalizationPipeline._compose_text(item.title, item.description)
        )
        feature_tokens: set[str] = signal["tokens"]
        if not item_tokens or not feature_tokens:
            return 0.0

        intersection = len(item_tokens.intersection(feature_tokens))
        denominator = max(len(item_tokens), len(feature_tokens))
        return float(intersection / denominator)

    def _link_score(self, left: MergedItemDTO, right: MergedItemDTO) -> float:
        left_text = self._compose_text(left.title, left.description)
        right_text = self._compose_text(right.title, right.description)

        left_tokens = self._tokenize(left_text)
        right_tokens = self._tokenize(right_text)
        overlap = 0.0
        if left_tokens and right_tokens:
            overlap = len(left_tokens.intersection(right_tokens)) / max(len(left_tokens), len(right_tokens))

        if overlap >= 0.25:
            return overlap

        left_embedding = self.embedder.embed(left_text)
        right_embedding = self.embedder.embed(right_text)
        return self.embedder.cosine_similarity(left_embedding, right_embedding)

    @staticmethod
    def _build_feature_signal(feature: CanonicalizationFeatureDTO) -> dict:
        aliases = [CanonicalizationPipeline._normalize_phrase(a) for a in feature.aliases]
        title_aliases = {
            CanonicalizationPipeline._normalize_phrase(feature.title),
            *[a for a in aliases if a],
        }
        embedding_text = CanonicalizationPipeline._compose_text(feature.title, feature.description)
        token_source = " ".join([feature.title, *(feature.aliases or []), feature.description or ""])
        tokens = CanonicalizationPipeline._tokenize(token_source)

        return {
            "title_aliases": {t for t in title_aliases if t},
            "tokens": tokens,
            "embedding_text": embedding_text,
        }

    @staticmethod
    def _normalize_phrase(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        # Unicode-aware tokenization to support multilingual text (including Vietnamese).
        raw_tokens = re.findall(r"\w+", (value or "").casefold(), flags=re.UNICODE)
        return {token for token in raw_tokens if len(token) > 1}

    @staticmethod
    def _compose_text(title: str, description: str | None) -> str:
        base = (title or "").strip()
        detail = (description or "").strip()
        return base if not detail else f"{base}\n{detail}"

    @staticmethod
    def _to_item(item: MergedItemDTO) -> CanonicalizationItemDTO:
        return CanonicalizationItemDTO(
            id=item.id,
            type=item.type,
            title=item.title,
            description=item.description,
            aliases=list(item.aliases),
            sources=list(item.sources),
            cluster_id=item.cluster_id,
        )

    @staticmethod
    def _to_feature(item: MergedItemDTO) -> CanonicalizationFeatureDTO:
        return CanonicalizationFeatureDTO(
            id=item.id,
            type=item.type,
            title=item.title,
            description=item.description,
            aliases=list(item.aliases),
            sources=list(item.sources),
            cluster_id=item.cluster_id,
            tasks=[],
            user_flows=[],
            apis=[],
            db_schemas=[],
        )

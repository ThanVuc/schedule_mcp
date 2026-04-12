
import re

from application.const.sprint_generation import SignalOrigin
from application.const.sprint_generation import (
    API_NORMALIZATION_PARAM_PATTERNS,
    API_NORMALIZATION_PREFIX_PATTERNS,
    API_SEGMENT_ALIAS_ALLOWLIST,
    NORMALIZATION_API_DESC_SIGNATURE_REGEX,
    NORMALIZATION_API_TITLE_METHOD_ENDPOINT_REGEX,
    NORMALIZATION_ENDPOINT_SUFFIX_REGEX,
    NORMALIZATION_NEAREST_SIMILARITY_MIN,
    NORMALIZATION_SINGLETON_SIMILARITY_MIN,
)
from application.dtos.sprint_generation_dto import (
    ExtractionModelDTO,
    NormalizationContentDTO,
    NormalizationResultDTO,
    NormalizedItemDTO,
    SignalItemDTO,
)
from infrastructure.base.embedder.embedder import Embedder


class NormalizationPipeline:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def normalize(
        self,
        data: list[ExtractionModelDTO],
    ) -> NormalizationResultDTO:
        features = self._normalize_features(data)
        tasks = self._normalize_tasks(data)
        apis = self._normalize_apis(data)
        database = self._normalize_db_schemas(data)

        self._attach_embeddings(features)
        self._attach_embeddings(tasks)
        self._attach_embeddings(apis)
        self._attach_embeddings(database)

        self._cluster_items(features)
        locked_tasks, mutable_tasks = self._split_locked_planning_tasks(tasks)
        self._cluster_items(mutable_tasks)
        self._cluster_items(apis)
        self._cluster_items(database)

        # Final semantic gate after embeddings + cluster metadata are available.
        self._apply_semantic_filter(features)
        self._apply_semantic_filter(mutable_tasks)
        # Skip semantic pruning for APIs; endpoint diversity creates many valid singleton signals.
        self._apply_semantic_filter(database)

        self._clear_embeddings(features)
        self._clear_embeddings(locked_tasks)
        self._clear_embeddings(mutable_tasks)
        self._clear_embeddings(apis)
        self._clear_embeddings(database)

        tasks = [*locked_tasks, *mutable_tasks]
        
        result = NormalizationResultDTO(
            features=features,
            tasks=tasks,
            apis=apis,
            database=database,
        )
        return result

    def _normalize_features(self, data: list[ExtractionModelDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for feature in source.features:
                items.append(
                    self._build_item(
                        item_id=f"F{counter}",
                        item_type="feature",
                        source=feature,
                        title=feature.title,
                        description=feature.description,
                    )
                )
                counter += 1
        return items

    def _normalize_tasks(self, data: list[ExtractionModelDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for task in source.tasks:
                description = task.description
                related_feature = task.metadata.get("related_feature") if isinstance(task.metadata, dict) else None
                if related_feature:
                    relation = f"Related feature: {related_feature}"
                    description = f"{description}\n{relation}" if description else relation

                items.append(
                    self._build_item(
                        item_id=f"T{counter}",
                        item_type="task",
                        source=task,
                        title=task.title,
                        description=description,
                    )
                )
                counter += 1
        return items

    def _normalize_apis(self, data: list[ExtractionModelDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for api in source.api:
                api_parts = [
                    str(api.metadata.get("method") or "").strip() or None,
                    str(api.metadata.get("endpoint") or "").strip() or None,
                ]
                signature = " ".join(part for part in api_parts if part)
                title = api.title.strip() if api.title and api.title.strip() else (signature or "unnamed api")

                details = [
                    f"Signature: {signature}" if signature else None,
                    api.description.strip() if api.description else None,
                ]
                description = "\n".join(part for part in details if part)

                items.append(
                    self._build_item(
                        item_id=f"A{counter}",
                        item_type="api",
                        source=api,
                        title=title,
                        description=description or None,
                    )
                )
                counter += 1
        return items

    def _normalize_db_schemas(self, data: list[ExtractionModelDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for table in source.databases:
                raw_columns = table.metadata.get("columns") if isinstance(table.metadata, dict) else []
                if not isinstance(raw_columns, list):
                    raw_columns = []
                summary_lines = [self._format_column(col) for col in raw_columns]
                description = "\n".join(line for line in summary_lines if line)

                items.append(
                    self._build_item(
                        item_id=f"DB{counter}",
                        item_type="db_schema",
                        source=table,
                        title=table.title,
                        description=description or None,
                    )
                )
                counter += 1
        return items

    @staticmethod
    def _format_column(column: dict) -> str:
        if not isinstance(column, dict):
            return ""
        column_name = str(column.get("name") or "").strip()
        if not column_name:
            return ""

        parts = [column_name]
        column_type = str(column.get("type") or "").strip()
        constraints = column.get("constraints") if isinstance(column.get("constraints"), list) else []
        if column_type:
            parts.append(f"type={column_type}")
        if constraints:
            parts.append(f"constraints={', '.join(str(c) for c in constraints if c)}")
        return " | ".join(parts)

    @staticmethod
    def _build_item(
        item_id: str,
        item_type: str,
        source: SignalItemDTO,
        title: str,
        description: str | None,
    ) -> NormalizedItemDTO:
        clean_title = (title or "").strip() or "untitled"
        clean_description = description.strip() if description else None

        return NormalizedItemDTO(
            id=item_id,
            type=item_type,
            signal_origin=source.signal_origin,
            content=NormalizationContentDTO(
                title=clean_title,
                description=clean_description,
            ),
            source_file_name=source.source_file_name,
            source_file_type=source.source_file_type,
        )

    def _attach_embeddings(self, items: list[NormalizedItemDTO]) -> None:
        if not items:
            return

        texts = [self._build_embedding_text(item) for item in items]
        vectors = self.embedder.embed_batch(texts)
        for item, vector in zip(items, vectors):
            item.embedding = vector

    @staticmethod
    def _build_embedding_text(item: NormalizedItemDTO) -> str:
        title = item.content.title.strip()
        description = item.content.description.strip() if item.content.description else ""
        return title if not description else f"{title}\n{description}"

    def _cluster_items(self, items: list[NormalizedItemDTO]) -> None:
        if not items:
            return

        if items[0].type == "api":
            self._cluster_api_items(items)
            return

        dedup_threshold = 0.9
        clusters: list[list[NormalizedItemDTO]] = []
        filtered_items: list[NormalizedItemDTO] = []
        for item in items:
            if not clusters:
                clusters.append([item])
                filtered_items.append(item)
                continue

            best_index = -1
            best_similarity = -1.0
            for idx, cluster in enumerate(clusters):
                score = self._avg_similarity(item, cluster)
                if score > best_similarity:
                    best_similarity = score
                    best_index = idx

            # Auto-drop near-duplicate items.
            if best_similarity > dedup_threshold:
                continue

            if best_similarity > 0.8 and best_index >= 0:
                clusters[best_index].append(item)
            else:
                clusters.append([item])
            filtered_items.append(item)

        items[:] = filtered_items

        for cluster_idx, cluster in enumerate(clusters, start=1):
            cluster_id = f"C{cluster_idx}"
            for item in cluster:
                item.cluster_id = cluster_id

    # Cluster APIs by deterministic signature key so different resources do not collapse together.
    def _cluster_api_items(self, items: list[NormalizedItemDTO]) -> None:
        clusters_by_signature: dict[str, list[NormalizedItemDTO]] = {}
        ordered_clusters: list[list[NormalizedItemDTO]] = []
        filtered_items: list[NormalizedItemDTO] = []

        for item in items:
            signature_key = self._api_signature_key(item)
            cluster = clusters_by_signature.get(signature_key)
            if cluster is None:
                clusters_by_signature[signature_key] = [item]
                ordered_clusters.append(clusters_by_signature[signature_key])
                filtered_items.append(item)
                continue

            # Strict structural dedupe for APIs: same signature means same endpoint contract.
            # Keep first occurrence to preserve deterministic source ordering.
            continue

        items[:] = filtered_items

        for cluster_idx, cluster in enumerate(ordered_clusters, start=1):
            cluster_id = f"C{cluster_idx}"
            for item in cluster:
                item.cluster_id = cluster_id

    # Keep explicit planning tasks as user-intent signals: never cluster or prune them.
    @staticmethod
    def _split_locked_planning_tasks(items: list[NormalizedItemDTO]) -> tuple[list[NormalizedItemDTO], list[NormalizedItemDTO]]:
        locked: list[NormalizedItemDTO] = []
        mutable: list[NormalizedItemDTO] = []

        for item in items:
            if (
                item.type == "task"
                and item.source_file_type.value == "Planning"
                and item.signal_origin == SignalOrigin.EXPLICIT
            ):
                locked.append(item)
            else:
                mutable.append(item)

        return locked, mutable

    # Build stable signature key from method + normalized endpoint extracted from title/description.
    @classmethod
    def _api_signature_key(cls, item: NormalizedItemDTO) -> str:
        method, endpoint = cls._extract_method_endpoint(item)
        endpoint_norm = cls._normalize_endpoint_for_signature(endpoint)
        return f"{method} {endpoint_norm}".strip()

    # Extract method and endpoint from normalized API title first, then signature line in description.
    @staticmethod
    def _extract_method_endpoint(item: NormalizedItemDTO) -> tuple[str, str]:
        title = str((item.content.title or "")).strip()
        title_match = re.search(NORMALIZATION_API_TITLE_METHOD_ENDPOINT_REGEX, title, flags=re.IGNORECASE)
        if title_match:
            return title_match.group(1).upper(), title_match.group(2)

        description = str((item.content.description or "")).strip()
        desc_match = re.search(
            NORMALIZATION_API_DESC_SIGNATURE_REGEX,
            description,
            flags=re.IGNORECASE,
        )
        if desc_match:
            return desc_match.group(1).upper(), desc_match.group(2)

        endpoint_match = re.search(NORMALIZATION_ENDPOINT_SUFFIX_REGEX, title)
        endpoint = endpoint_match.group(1) if endpoint_match else title
        return "", endpoint

    # Normalize endpoint key to merge only true equivalences (strip version prefix, normalize placeholders).
    @staticmethod
    def _normalize_endpoint_for_signature(endpoint: str) -> str:
        value = str(endpoint or "").strip().lower()
        if not value:
            return ""

        value = re.sub(r"/{2,}", "/", value)
        if not value.startswith("/"):
            value = f"/{value}"

        # Controlled prefix stripping for transport/version-only path prefixes.
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
        value = re.sub(r"/{2,}", "/", value)
        return value or "/"

    def _avg_similarity(self, item: NormalizedItemDTO, cluster: list[NormalizedItemDTO]) -> float:
        if not item.embedding:
            return 0.0

        valid_cluster_items = [member for member in cluster if member.embedding]
        if not valid_cluster_items:
            return 0.0

        similarities = [
            self.embedder.cosine_similarity(item.embedding, member.embedding)
            for member in valid_cluster_items
        ]
        if not similarities:
            return 0.0

        return sum(similarities) / len(similarities)

    def _apply_semantic_filter(self, items: list[NormalizedItemDTO]) -> None:
        if not items:
            return

        filtered: list[NormalizedItemDTO] = []
        for item in items:
            nearest_similarity = self._nearest_similarity(item, items)
            if nearest_similarity < NORMALIZATION_NEAREST_SIMILARITY_MIN:
                continue

            if self._is_isolated_singleton(item, items):
                if nearest_similarity < NORMALIZATION_SINGLETON_SIMILARITY_MIN:
                    continue

            filtered.append(item)

        items[:] = filtered

    def _nearest_similarity(self, item: NormalizedItemDTO, items: list[NormalizedItemDTO]) -> float:
        if not item.embedding:
            return 0.0

        other_embeddings = [candidate.embedding for candidate in items if candidate is not item and candidate.embedding]
        if not other_embeddings:
            # No comparison context: keep the item by similarity threshold.
            return 1.0

        return self.embedder.cosine_to_nearest_similarity(item.embedding, other_embeddings)

    @staticmethod
    def _is_isolated_singleton(item: NormalizedItemDTO, items: list[NormalizedItemDTO]) -> bool:
        if not item.cluster_id:
            return True

        cluster_size = sum(1 for candidate in items if candidate.cluster_id == item.cluster_id)
        return cluster_size <= 1

    @staticmethod
    def _clear_embeddings(items: list[NormalizedItemDTO]) -> None:
        for item in items:
            item.embedding = None

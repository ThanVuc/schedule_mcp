
from application.dtos.sprint_generation_dto import (
    ClassificationResultDTO,
    ColumnDTO,
    NormalizationContentDTO,
    NormalizationResultDTO,
    NormalizationSourceDTO,
    NormalizedItemDTO,
)
from infrastructure.base.embedder.embedder import Embedder


class NormalizationPipeline:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def normalize(
        self,
        data: list[ClassificationResultDTO],
    ) -> NormalizationResultDTO:
        features = self._normalize_features(data)
        tasks = self._normalize_tasks(data)
        user_flows = self._normalize_user_flows(data)
        apis = self._normalize_apis(data)
        db_schemas = self._normalize_db_schemas(data)

        self._attach_embeddings(features)
        self._attach_embeddings(tasks)
        self._attach_embeddings(user_flows)
        self._attach_embeddings(apis)
        self._attach_embeddings(db_schemas)

        self._cluster_items(features)
        self._cluster_items(tasks)
        self._cluster_items(user_flows)
        self._cluster_items(apis)
        self._cluster_items(db_schemas)

        self._clear_embeddings(features)
        self._clear_embeddings(tasks)
        self._clear_embeddings(user_flows)
        self._clear_embeddings(apis)
        self._clear_embeddings(db_schemas)
        
        result = NormalizationResultDTO(
            features=features,
            tasks=tasks,
            user_flows=user_flows,
            apis=apis,
            db_schemas=db_schemas,
        )
        return result

    def _normalize_features(self, data: list[ClassificationResultDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for feature in source.features:
                items.append(
                    self._build_item(
                        item_id=f"F{counter}",
                        item_type="feature",
                        source=source,
                        title=feature.title,
                        description=feature.description,
                    )
                )
                counter += 1
        return items

    def _normalize_tasks(self, data: list[ClassificationResultDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for task in source.tasks:
                description = task.description
                if task.related_feature:
                    relation = f"Related feature: {task.related_feature}"
                    description = f"{description}\n{relation}" if description else relation

                items.append(
                    self._build_item(
                        item_id=f"T{counter}",
                        item_type="task",
                        source=source,
                        title=task.title,
                        description=description,
                    )
                )
                counter += 1
        return items

    def _normalize_user_flows(self, data: list[ClassificationResultDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for flow in source.user_flows:
                steps = [step.strip() for step in flow.steps if step and step.strip()]
                description = "\n".join(f"{idx}. {step}" for idx, step in enumerate(steps, start=1))

                items.append(
                    self._build_item(
                        item_id=f"UF{counter}",
                        item_type="user_flow",
                        source=source,
                        title=flow.name,
                        description=description or None,
                    )
                )
                counter += 1
        return items

    def _normalize_apis(self, data: list[ClassificationResultDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for api in source.apis:
                api_parts = [
                    api.method.strip() if api.method else None,
                    api.endpoint.strip() if api.endpoint else None,
                ]
                signature = " ".join(part for part in api_parts if part)
                title = api.name.strip() if api.name and api.name.strip() else (signature or "unnamed api")

                details = [
                    f"Signature: {signature}" if signature else None,
                    api.description.strip() if api.description else None,
                ]
                description = "\n".join(part for part in details if part)

                items.append(
                    self._build_item(
                        item_id=f"A{counter}",
                        item_type="api",
                        source=source,
                        title=title,
                        description=description or None,
                    )
                )
                counter += 1
        return items

    def _normalize_db_schemas(self, data: list[ClassificationResultDTO]) -> list[NormalizedItemDTO]:
        items: list[NormalizedItemDTO] = []
        counter = 1
        for source in data:
            for table in source.db_schema:
                summary_lines = [self._format_column(col) for col in table.columns]
                description = "\n".join(line for line in summary_lines if line)

                items.append(
                    self._build_item(
                        item_id=f"DB{counter}",
                        item_type="db_schema",
                        source=source,
                        title=table.table,
                        description=description or None,
                    )
                )
                counter += 1
        return items

    @staticmethod
    def _format_column(column: ColumnDTO) -> str:
        parts = [column.name]
        if column.type:
            parts.append(f"type={column.type}")
        if column.constraints:
            parts.append(f"constraints={', '.join(column.constraints)}")
        return " | ".join(parts)

    @staticmethod
    def _build_item(
        item_id: str,
        item_type: str,
        source: ClassificationResultDTO,
        title: str,
        description: str | None,
    ) -> NormalizedItemDTO:
        clean_title = (title or "").strip() or "untitled"
        clean_description = description.strip() if description else None

        return NormalizedItemDTO(
            id=item_id,
            type=item_type,
            content=NormalizationContentDTO(
                title=clean_title,
                description=clean_description,
            ),
            source=NormalizationSourceDTO(
                file_name=source.file_name,
                type=source.type,
            ),
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

    @staticmethod
    def _clear_embeddings(items: list[NormalizedItemDTO]) -> None:
        for item in items:
            item.embedding = None

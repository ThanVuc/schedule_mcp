
import asyncio

from application.dtos.common import FileDTO
from application.dtos.sprint_generation_dto import (
    AISprintGenerationRequestedPayloadDTO,
    AISprintGenerationResultTaskDTO,
    CanonicalizationResultDTO,
    ClassificationResultDTO,
    NormalizationResultDTO,
    ReconciliationResultDTO,
)
from application.pipeline.sprint_generation.canonicalization import CanonicalizationPipeline
from application.pipeline.sprint_generation.classification_and_extraction import ClassifyAndExtractPipeline
from application.pipeline.sprint_generation.ingestion import IngestionPipeline
from application.pipeline.sprint_generation.normalization import NormalizationPipeline
from application.pipeline.sprint_generation.reconciliation import ReconciliationPipeline
from application.pipeline.sprint_generation.task_generation import TaskGenerationPipeline
from infrastructure.container import InfrastructureContainer


class SprintGenerationPipeline:
    def __init__(self, infra: InfrastructureContainer, max_concurrency: int = 5):
        self._infra = infra
        self.storage = infra.get_storage()
        self.llm = infra.get_llm_connector()
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
    
    async def ingest(self, objects_key: list[str]) -> list[FileDTO]:
        return await IngestionPipeline(
            storage=self.storage,
            llm=self.llm,
            max_concurrency=self.max_concurrency,
        ).ingest(objects_key)

    async def classify_and_extract(self, file_dtos: list[FileDTO]) -> list[ClassificationResultDTO]:
        return await ClassifyAndExtractPipeline(
            infra=self._infra,
            max_concurrency=self.max_concurrency,
        ).classify_and_extract(file_dtos)

    async def normalize(
        self,
        classification_results: list[ClassificationResultDTO],
    ) -> NormalizationResultDTO:
        return NormalizationPipeline(
            embedder=self._infra.get_embedder(),
        ).normalize(
            data=classification_results,
        )

    async def reconcile(
        self,
        normalization_result: NormalizationResultDTO,
    ) -> ReconciliationResultDTO:
        return await ReconciliationPipeline(
            llm=self.llm,
            max_concurrency=self.max_concurrency,
        ).reconcile(
            data=normalization_result,
        )

    async def canonicalize(
        self,
        reconciliation_result: ReconciliationResultDTO,
    ) -> CanonicalizationResultDTO:
        return CanonicalizationPipeline(
            embedder=self._infra.get_embedder(),
        ).canonicalize(
            items=reconciliation_result,
        )

    async def generate_tasks(
        self,
        canonicalization_result: CanonicalizationResultDTO,
        payload: AISprintGenerationRequestedPayloadDTO,
    ) -> list[AISprintGenerationResultTaskDTO]:
        return await TaskGenerationPipeline(
            llm=self.llm,
        ).generate_tasks(
            canonicalization=canonicalization_result,
            payload=payload,
        )

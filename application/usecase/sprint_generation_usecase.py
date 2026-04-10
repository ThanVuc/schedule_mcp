import logging

from application.dtos.sprint_generation_dto import (
    AISprintGenerationRequestedMessageDTO,
    AISprintGenerationResultMessageDTO,
    AISprintGenerationResultPayloadDTO,
    AISprintGenerationResultTaskDTO,
    TeamNotificationMessageDTO,
    TeamNotificationMetadataDTO,
    TeamNotificationPayloadDTO,
)
from application.pipeline.sprint_generation.pipeline import SprintGenerationPipeline
from application.publisher.sprint_result_publisher import SprintResultPublisher
from application.publisher.team_notification_publisher import TeamNotificationPublisher
from constant.notification import (
    CORRELATION_TYPE_SPRINT,
    EVENT_TYPE_SPRINT_GENERATION_FAILED,
)


class SprintGenerationUseCase:
    def __init__(
        self,
        sprint_result_publisher: SprintResultPublisher,
        team_notification_publisher: TeamNotificationPublisher,
        sprint_generation_pipeline: SprintGenerationPipeline,
    ):
        self.sprint_result_publisher = sprint_result_publisher
        self.team_notification_publisher = team_notification_publisher
        self.sprint_generation_pipeline = sprint_generation_pipeline

    async def process_sprint_generation_request(self, dto: AISprintGenerationRequestedMessageDTO):
        try:
            # Pipeline
            ## Step 1: Ingest and process input files (e.g. backlog.csv) - placeholder for now
            ingested_objects = await self.sprint_generation_pipeline.ingest(
                [f.object_key for f in dto.payload.files]
            )

            ## Step 2: Classification & Extraction (1 file = 1 async LLM call)
            classification_results = await self.sprint_generation_pipeline.classify_and_extract(
                ingested_objects
            )

            ## Step 3: Normalization (embedding, similarity, clustering)
            normalization_result = await self.sprint_generation_pipeline.normalize(
                classification_results,
            )

            ## Step 4: Reconciliation (cluster filtering + AI merge)
            reconciliation_result = await self.sprint_generation_pipeline.reconcile(
                normalization_result,
            )

            ## Step 5: Canonicalization (feature-centered linking + orphan preserving)
            canonicalization_result = await self.sprint_generation_pipeline.canonicalize(
                reconciliation_result,
            )

            ## Step 6: Task Generation
            generated_tasks = await self.sprint_generation_pipeline.generate_tasks(
                canonicalization_result=canonicalization_result,
                payload=dto.payload,
            )

            # Build response envelope from pipeline output.
            result_message = self._build_success_result_message(
                dto=dto,
                generated_tasks=generated_tasks,
            )

            await self.sprint_result_publisher.publish(result_message)
        except Exception:
            logging.exception(
                "failed to publish sprint generation result | job_id=%s | group_id=%s",
                dto.job_id,
                dto.group_id,
            )
            await self._publish_error_notification(dto)
            raise

    async def _publish_error_notification(
        self,
        dto: AISprintGenerationRequestedMessageDTO,
    ):
        notification_message = TeamNotificationMessageDTO(
            event_type=EVENT_TYPE_SPRINT_GENERATION_FAILED,
            sender_id="ai-service",
            receiver_ids=[dto.sender_id],
            payload=TeamNotificationPayloadDTO(
                title="Sprint generation failed",
                message="Không thể tạo sprint, vui lòng thử lại sau.",
                correlation_id=dto.group_id,
                correlation_type=CORRELATION_TYPE_SPRINT,
                link="/groups",
                img_url=None,
            ),
            metadata=TeamNotificationMetadataDTO(
                is_send_mail=True,
            ),
        )

        await self.team_notification_publisher.publish(notification_message)

    @staticmethod
    def _build_success_result_message(
        dto: AISprintGenerationRequestedMessageDTO,
        generated_tasks: list[AISprintGenerationResultTaskDTO],
    ) -> AISprintGenerationResultMessageDTO:
        return AISprintGenerationResultMessageDTO(
            event_type="SPRINT_GENERATION_COMPLETED",
            job_id=dto.job_id,
            group_id=dto.group_id,
            sender_id=dto.sender_id,
            payload=AISprintGenerationResultPayloadDTO(
                status="SUCCESS",
                sprint=dto.payload.sprint,
                tasks=generated_tasks,
            ),
        )

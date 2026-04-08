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
            logging.info(
                "starting sprint ingestion | job_id=%s | files=%d",
                dto.job_id,
                len(dto.payload.files),
            )
            ingested_objects = await self.sprint_generation_pipeline.ingest(
                [f.object_key for f in dto.payload.files]
            )
            logging.info(
                "completed sprint ingestion | job_id=%s | ingested=%d",
                dto.job_id,
                len(ingested_objects),
            )


            ## Step 2: Classification & Extraction (1 file = 1 async LLM call)
            logging.info(
                "starting classify_and_extract | job_id=%s | files=%d",
                dto.job_id,
                len(ingested_objects),
            )
            classification_results = await self.sprint_generation_pipeline.classify_and_extract(
                ingested_objects
            )
            logging.info(
                "completed classify_and_extract | job_id=%s | results=%d",
                dto.job_id,
                len(classification_results),
            )

            ## Step 3: Normalization (embedding, similarity, clustering)
            logging.info(
                "starting normalization | job_id=%s | results=%d",
                dto.job_id,
                len(classification_results),
            )
            normalization_result = await self.sprint_generation_pipeline.normalize(
                classification_results,
                evidence_name=dto.job_id,
            )
            logging.info(
                (
                    "completed normalization | job_id=%s | features=%d | tasks=%d "
                    "| user_flows=%d | apis=%d | db_schemas=%d"
                ),
                dto.job_id,
                len(normalization_result.features),
                len(normalization_result.tasks),
                len(normalization_result.user_flows),
                len(normalization_result.apis),
                len(normalization_result.db_schemas),
            )

            ## Step 4: Reconciliation (cluster filtering + AI merge)
            logging.info(
                "starting reconciliation | job_id=%s",
                dto.job_id,
            )
            reconciliation_result = await self.sprint_generation_pipeline.reconcile(
                normalization_result,
                evidence_name=dto.job_id,
            )
            logging.info(
                (
                    "completed reconciliation | job_id=%s | features=%d | tasks=%d "
                    "| user_flows=%d | apis=%d | db_schemas=%d"
                ),
                dto.job_id,
                len(reconciliation_result.features),
                len(reconciliation_result.tasks),
                len(reconciliation_result.user_flows),
                len(reconciliation_result.apis),
                len(reconciliation_result.db_schemas),
            )

            ## Step 5: Canonicalization (feature-centered linking + orphan preserving)
            logging.info(
                "starting canonicalization | job_id=%s",
                dto.job_id,
            )
            canonicalization_result = await self.sprint_generation_pipeline.canonicalize(
                reconciliation_result,
                evidence_name=dto.job_id,
            )
            logging.info(
                (
                    "completed canonicalization | job_id=%s | features=%d | orphan_tasks=%d "
                    "| orphan_user_flows=%d | orphan_apis=%d | orphan_db_schemas=%d"
                ),
                dto.job_id,
                len(canonicalization_result.features),
                len(canonicalization_result.tasks),
                len(canonicalization_result.user_flows),
                len(canonicalization_result.apis),
                len(canonicalization_result.db_schemas),
            )

            ## Step 6: Task Generation
            logging.info(
                "starting task generation | job_id=%s",
                dto.job_id,
            )
            generated_tasks = await self.sprint_generation_pipeline.generate_tasks(
                canonicalization_result=canonicalization_result,
                payload=dto.payload,
                evidence_name=dto.job_id,
            )
            logging.info(
                "completed task generation | job_id=%s | generated_tasks=%d",
                dto.job_id,
                len(generated_tasks),
            )

            # Build response envelope from pipeline output.
            result_message = self._build_success_result_message(
                dto=dto,
                generated_tasks=generated_tasks,
            )

            await self.sprint_result_publisher.publish(result_message)
        except Exception as exc:
            logging.exception(
                "failed to publish sprint generation result | job_id=%s | group_id=%s",
                dto.job_id,
                dto.group_id,
            )
            await self._publish_error_notification(dto, str(exc))
            raise

    async def _publish_error_notification(
        self,
        dto: AISprintGenerationRequestedMessageDTO,
        error_detail: str,
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

        # Keep additional error detail out of user-facing payload for now and only log it.
        logging.error(
            "publish sprint generation failed notification | job_id=%s | detail=%s",
            dto.job_id,
            error_detail,
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

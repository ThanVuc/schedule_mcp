import logging

from application.dtos.sprint_generation_dto import (
    AISprintGenerationRequestedMessageDTO,
    AISprintGenerationResultMessageDTO,
    AISprintGenerationResultPayloadDTO,
    TeamNotificationMessageDTO,
    TeamNotificationMetadataDTO,
    TeamNotificationPayloadDTO,
)
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
    ):
        self.sprint_result_publisher = sprint_result_publisher
        self.team_notification_publisher = team_notification_publisher

    async def process_sprint_generation_request(self, dto: AISprintGenerationRequestedMessageDTO):
        try:
            # MQ-only skeleton: keep request/response envelope and publish a success result back to Team service.
            result_message = AISprintGenerationResultMessageDTO(
                event_type="SPRINT_GENERATION_COMPLETED",
                job_id=dto.job_id,
                group_id=dto.group_id,
                sender_id=dto.sender_id,
                payload=AISprintGenerationResultPayloadDTO(
                    status="SUCCESS",
                    sprint=dto.payload.sprint,
                    tasks=[],
                ),
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

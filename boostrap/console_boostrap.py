import asyncio
import logging

from application.dtos.sprint_generation_dto import (
	AISprintGenerationRequestedMessageDTO,
	AISprintGenerationRequestedPayloadDTO,
)
from application.pipeline.sprint_generation.pipeline import SprintGenerationPipeline
from application.usecase.sprint_generation_usecase import SprintGenerationUseCase
from boostrap.di import DIContainer
from infrastructure.base.logging.config import setup_logging


class LogSprintResultPublisher:
	async def publish(self, message):
		logging.info(
			"[CONSOLE TEST] Sprint result publish bypassed MQ | payload=%s",
			message.model_dump(mode="json", exclude_none=True),
		)


class LogTeamNotificationPublisher:
	async def publish(self, message):
		logging.info(
			"[CONSOLE TEST] Team notification publish bypassed MQ | payload=%s",
			message.model_dump(mode="json", exclude_none=True),
		)


def _build_hardcoded_message() -> AISprintGenerationRequestedMessageDTO:
	payload = AISprintGenerationRequestedPayloadDTO.model_validate(
		{
			"sprint": {
				"name": "Sprint 2026-W15",
				"goal": "Improve onboarding flow",
				"start_date": "2026-04-07",
				"end_date": "2026-04-20",
			},
			"files": [
				{
					"object_key": "ai-sprint-generation/Design-LLD-Phase 2 (9).md",
					"size": 1024,
				},
				{
					"object_key": "ai-sprint-generation/Requirement_Export Srpint Requirement Analysis (2).docx",
					"size": 1024,
				},
				{
					"object_key": "ai-sprint-generation/planning_sprint_11111111-2222-3333-4444-555555555555.xlsx",
					"size": 1024,
				}
			],
			"additional_context": "Focus on high-impact tasks first, and using the Vietnamese language for task descriptions is preferred.",
		}
	)

	return AISprintGenerationRequestedMessageDTO(
		event_type="SPRINT_GENERATION_REQUESTED",
		job_id="console-job-001",
		group_id="demo-group",
		sender_id="demo-user",
		payload=payload,
	)


async def ConsoleBootstrapApplication():
	setup_logging()

	logging.info("=== Sprint Generation Console Test (Hardcoded Input) ===")
	dto = _build_hardcoded_message()
	logging.info("Hardcoded request DTO: %s", dto.model_dump(mode="json", exclude_none=True))
	di = DIContainer()
	pipeline = SprintGenerationPipeline(di.infrastructure_container)

	usecase = SprintGenerationUseCase(
		sprint_result_publisher=LogSprintResultPublisher(),
		team_notification_publisher=LogTeamNotificationPublisher(),
		sprint_generation_pipeline=pipeline,
	)

	try:
		await usecase.process_sprint_generation_request(dto)
		logging.info("Sprint generation usecase executed successfully in console test mode.")
	except Exception as exc:
		logging.exception("Sprint generation usecase failed in console test mode: %s", exc)
	finally:
		logging.info("=== End of Sprint Generation Console Test ===")
		await di.shutdown()



if __name__ == "__main__":
	asyncio.run(ConsoleBootstrapApplication())

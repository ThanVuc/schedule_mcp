from application.pipeline.sprint_generation.pipeline import SprintGenerationPipeline
from application.publisher.container import PublisherContainer
from application.usecase.sprint_generation_usecase import SprintGenerationUseCase
from application.usecase.work_generation_usecase import WorkGenerationUseCase
from infrastructure.base.llm.gemini_llm import LLMConnector
from infrastructure.container import InfrastructureContainer

class UseCaseContainer:
    def __init__(
            self,
            infra: InfrastructureContainer,
            publisher_container: PublisherContainer,
            sprint_generation_pipeline: SprintGenerationPipeline,
    ):
        self.work_generation_usecase = WorkGenerationUseCase(
            infra.get_llm_connector(),
            publisher_container.notification_publisher,
            publisher_container.work_transfer_publisher,
        )
        self.sprint_generation_usecase = SprintGenerationUseCase(
            sprint_result_publisher=publisher_container.sprint_result_publisher,
            team_notification_publisher=publisher_container.team_notification_publisher,
            sprint_generation_pipeline=sprint_generation_pipeline,
        )

from application.publisher.container import PublisherContainer
from application.usecase.work_generation_usecase import WorkGenerationUseCase
from infrastructure.base.llm.gemini_llm import LLMConnector
from infrastructure.container import InfrastructureContainer

class UseCaseContainer:
    def __init__(
            self,
            infra: InfrastructureContainer,
            publisher_container: PublisherContainer
    ):
        self.work_generation_usecase = WorkGenerationUseCase(
            infra.get_llm_connector(),
            publisher_container.notification_publisher,
            publisher_container.work_transfer_publisher,
        )

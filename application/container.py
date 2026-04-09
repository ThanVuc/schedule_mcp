from application.pipeline.sprint_generation.pipeline import SprintGenerationPipeline
from application.publisher.container import PublisherContainer
from application.usecase.container import UseCaseContainer
from infrastructure.container import InfrastructureContainer


class ApplicationContainer:
    def __init__(
            self,
            infrastructure: InfrastructureContainer,
            publisher_container: PublisherContainer,
            sprint_generation_pipeline: SprintGenerationPipeline | None = None,
    ):
        self.publisher_container = publisher_container
        pipeline = sprint_generation_pipeline or SprintGenerationPipeline(infrastructure)
        self.usecase_container = UseCaseContainer(
            infrastructure,
            self.publisher_container,
            pipeline,
        )

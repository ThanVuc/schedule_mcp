
from application.pipeline.sprint_generation.pipeline import SprintGenerationPipeline
from infrastructure.container import InfrastructureContainer


class PipelineContainer:
        def __init__(
                self,
                infrastructure: InfrastructureContainer,
        ):
            self.sprint_generation_pipeline = SprintGenerationPipeline(infrastructure)
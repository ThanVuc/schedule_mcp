from application.publisher.container import PublisherContainer
from application.usecase.container import UseCaseContainer
from infrastructure.container import InfrastructureContainer


class ApplicationContainer:
    def __init__(
            self,
            infrastructure: InfrastructureContainer,
            publisher_container: PublisherContainer
    ):
        self.publisher_container = publisher_container
        self.usecase_container = UseCaseContainer(infrastructure, self.publisher_container)

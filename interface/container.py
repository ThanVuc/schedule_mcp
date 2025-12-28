
from domain.container import DomainContainer
from infrastructure.container import InfrastructureContainer
from interface.base import Runnable


class InterfaceContainer:
    def __init__(self, infrastructure: InfrastructureContainer, domain: DomainContainer):
        self.infrastructure = infrastructure
        self.domain = domain
        self.__runables: list[Runnable] = []
    
    def add_consumer(self, consumer: Runnable) -> None:
        """Register a consumer to be run later."""
        self.__runables.append(consumer)
    
    def get_consumers(self):
        return self.__runables

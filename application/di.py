from domain import DomainContainer
from infrastructure import InfrastructureContainer
from interface import InterfaceContainer


class DIContainer:
    def __init__(self):
        self.__infrastructure = None
        self.__domain = None
        self.__interface = None
    
    @property
    def infrastructure_container(self) -> InfrastructureContainer:
        """Lazy load and cache infrastructure container"""
        if self.__infrastructure is None:
            self.__infrastructure = InfrastructureContainer()
        return self.__infrastructure
    
    @property
    def domain_container(self) -> DomainContainer:
        """Lazy load and cache domain container"""
        if self.__domain is None:
            self.__domain = DomainContainer(self.infrastructure_container)
        return self.__domain
    
    @property
    def interface_container(self) -> InterfaceContainer:
        """Lazy load and cache interface container"""
        if self.__interface is None:
            self.__interface = InterfaceContainer(self.infrastructure_container, self.domain_container)
        return self.__interface
    
    def run_consumers(self):
        """Run all registered consumers"""
        for consumer in self.interface_container.get_consumers():
            consumer.run()

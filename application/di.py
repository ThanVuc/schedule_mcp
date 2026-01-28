from domain import DomainContainer
from infrastructure import InfrastructureContainer
from infrastructure.base.configuration.settings import InitSettings, Settings
from infrastructure.base.logging.config import setup_logging
from interface import InterfaceContainer
from interface.consumer import WorkGenerationConsumer


class DIContainer:
    def __init__(self):
        # settings
        self.__settings = None

        # cache containers
        self.__infrastructure = None
        self.__domain = None
        self.__interface = None

        # flag
        self.__consumers_registered = False

    @property
    def settings(self) -> Settings:
        """Application settings"""
        if self.__settings is None:
            self.__settings = InitSettings()
        return self.__settings
    
    @property
    def infrastructure_container(self) -> InfrastructureContainer:
        """Lazy load and cache infrastructure container"""
        if self.__infrastructure is None:
            self.__infrastructure = InfrastructureContainer(settings=self.settings)
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
            self.__interface = InterfaceContainer(
                # self.infrastructure_container, 
                # self.domain_container
            )

        return self.__interface
    
    def _wire_consumer(self):
        """Initialize all consumers"""
        if self.__consumers_registered:
            return

        interface = self.interface_container
        infrastructure = self.infrastructure_container

        # work generation consumer
        work_consumer = WorkGenerationConsumer(
            mq_connector=infrastructure.get_mq_connector(),
        )
        interface.consumer_interface.add_consumer(work_consumer)

        self.__consumers_registered = True

    def wire(self):
        """Wire all components together"""
        # setup
        setup_logging()

        # ensure all containers are initialized
        _ = self.settings
        _ = self.infrastructure_container
        _ = self.domain_container
        _ = self.interface_container

        # wire consumers
        self._wire_consumer()

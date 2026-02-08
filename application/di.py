from application.container import ApplicationContainer
from application.publisher.container import PublisherContainer
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
        self.__interface = None
        self.__application = None

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
    def interface_container(self) -> InterfaceContainer:
        """Lazy load and cache interface container"""
        if self.__interface is None:
            self.__interface = InterfaceContainer()

        return self.__interface
    
    @property
    def application_container(self) -> ApplicationContainer:
        if self.__application is None:
            raise RuntimeError("ApplicationContainer not initialized. Call wire() first.")
        return self.__application

    async def _wire_consumer(self):
        """Initialize all consumers"""
        if self.__consumers_registered:
            return

        interface = self.interface_container
        infrastructure = self.infrastructure_container

        # work generation consumer
        work_consumer = WorkGenerationConsumer(
            mq_connector=infrastructure.get_mq_connector(),
            work_generation_usecase=self.application_container.usecase_container.work_generation_usecase,
            notification_publisher=self.application_container.publisher_container.notification_publisher,
        )
        
        interface.consumer_interface.add_consumer(work_consumer)

        self.__consumers_registered = True

    async def wire(self):
        setup_logging()

        _ = self.settings
        _ = self.infrastructure_container
        _ = self.interface_container

        # init publishers
        if self.__application is not None:
            return  # already wired

        publisher_container = PublisherContainer()
        await publisher_container.init(
            self.infrastructure_container.get_mq_connector()
        )

        # init application container
        self.__application = ApplicationContainer(
            infrastructure=self.infrastructure_container,
            publisher_container=publisher_container,
        )

        # wire consumers
        await self._wire_consumer()

from infrastructure.base.configuration import Settings
from .base import BaseInfrastructureContainer

class InfrastructureContainer:
    def __init__(self, settings: Settings):
        self.base_container = BaseInfrastructureContainer(settings=settings)
    
    def get_mq_connector(self):
        return self.base_container.mq_container.mq_connector

    def get_llm_connector(self):
        return self.base_container.llm_container.llm_connector
    

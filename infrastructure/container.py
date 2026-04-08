from infrastructure.base.configuration import Settings
from .base import BaseInfrastructureContainer

class InfrastructureContainer:
    def __init__(self, settings: Settings):
        self.base_container = BaseInfrastructureContainer(settings=settings)
    
    def get_mq_connector(self):
        return self.base_container.mq_container.mq_connector

    def get_llm_connector(self):
        return self.base_container.llm_container.llm_connector

    def get_embedder(self):
        return self.base_container.embedder

    def get_storage(self):
        return self.base_container.storage

    async def close(self):
        await self.base_container.close()
    

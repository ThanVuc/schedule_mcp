from infrastructure.base.configuration.settings import Settings
from infrastructure.base.embedder.embedder import Embedder
from infrastructure.base.llm.container import LLMContainer
from infrastructure.base.mq.container import MQContainer
from infrastructure.base.storage.storage import Storage

class BaseInfrastructureContainer:
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mq_container = MQContainer(self.settings.mq)
        self.llm_container = LLMContainer(self.settings.llm)
        self.embedder = Embedder(self.settings.embedder)
        self.storage = Storage(self.settings.storage)

    async def close(self) -> None:
        await self.llm_container.close()
        await self.mq_container.mq_connector.close()

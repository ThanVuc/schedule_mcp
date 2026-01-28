from infrastructure.base.configuration.settings import Settings
from infrastructure.base.llm.container import LLMContainer
from infrastructure.base.mq.container import MQContainer

class BaseInfrastructureContainer:
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mq_container = MQContainer(self.settings.mq)
        self.llm_container = LLMContainer(self.settings.llm)

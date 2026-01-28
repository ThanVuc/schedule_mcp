from application.settings import LLMSettings
from infrastructure.base.llm.gemini_llm import LLMConnector


class LLMContainer:
    def __init__(self, llm_settings: LLMSettings):
        self.llm_connector = LLMConnector(llm_settings)

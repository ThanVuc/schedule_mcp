from application.settings import LLMSettings
from google import genai
from google.genai import types


class LLMConnector:
    def __init__(self, llm_settings: LLMSettings):
        self.__api_key = llm_settings.api_key
        self.__model = llm_settings.model
        self.__client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self.__client is None:
            if not self.__api_key:
                raise ValueError("Gemini API key is not set in LLM settings.")
            self.__client = genai.Client(api_key=self.__api_key)
        return self.__client

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        max_output_tokens: int = 1024,
        enable_thinking: bool = True,
    ):
        client = self._get_client()

        generation_config = types.GenerationConfig(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_output_tokens=max_output_tokens,
        )

        thinking_config = types.ThinkingConfig(
            enable_thinking=enable_thinking
        )

        response = client.models.generate_content(
            model=self.__model,
            contents=prompt,
            generation_config=generation_config,
            thinking_config=thinking_config,
        )

        return response

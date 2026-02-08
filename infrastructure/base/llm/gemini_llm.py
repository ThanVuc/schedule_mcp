import asyncio
import time

from aio_pika import logger
import aiohttp
from application.settings import LLMSettings
from google import genai
from google.genai import types


class LLMConnector:
    def __init__(self, llm_settings: LLMSettings):
        self.__api_key = llm_settings.api_key
        self.__model = llm_settings.model
        self.__client: genai.Client | None = None
        self.__url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.__model}:generateContent"
        self.__session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.__api_key,
            },
            connector=aiohttp.TCPConnector(keepalive_timeout=300)
        )

    def _get_client(self) -> genai.Client:
        if self.__client is None:
            if not self.__api_key:
                raise ValueError("Gemini API key is not set in LLM settings.")
            self.__client = genai.Client(api_key=self.__api_key)
        return self.__client

    async def sdk_generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        max_output_tokens: int = 1024,
        timeout_seconds: float = 30.0,
    ):
        client = self._get_client()

        generation_config = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "max_output_tokens": max_output_tokens,
        }

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self.__model,
                    contents=prompt,
                    config=generation_config,
                ),
                timeout=timeout_seconds,
            )

            return response

        except asyncio.TimeoutError:
            logger.error(
                "LLM generate timeout | model=%s | timeout=%.1fs | prompt_len=%d",
                self.__model,
                timeout_seconds,
                len(prompt),
            )
            raise
        except Exception as e:
            logger.exception(
                "LLM generate unknown error | model=%s | prompt_len=%d",
                self.__model,
                len(prompt),
            )
            raise

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        max_output_tokens: int = 1024,
        timeout_seconds: float = 60.0,
        afc_enabled: bool = False,
    ):
        # 1. Cấu hình Headers
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.__api_key,
        }

        # 2. Xây dựng Payload (bao gồm tắt AFC bằng mode: NONE)
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "topP": top_p,
                "topK": top_k,
                "maxOutputTokens": max_output_tokens,
            },
            "toolConfig": {
                "function_calling_config": {
                    "mode": "NONE" if not afc_enabled else "AUTO"
                }
            }
        }

        # 3. Thực hiện gọi API
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        
        try:
            start = time.monotonic()
            async with self.__session.post(
                self.__url,
                json=payload,
                headers=headers,
                timeout=timeout
            ) as response:
                if response.status != 200:
                    if response.status == 429:
                        logger.error(
                            "LLM rate limit exceeded | model=%s | status=%d | prompt_len=%d",
                            self.__model, response.status, len(prompt),
                        )
                        raise Exception("LLM rate limit exceeded")

                    logger.error(
                        "LLM generate error | model=%s | status=%d | prompt_len=%d",
                        self.__model, response.status, len(prompt),
                    )
                    raise Exception(f"LLM generate error with status code {response.status}")
                data = await response.json()
                content = data['candidates'][0]['content']['parts'][0]['text']
                logger.info(
                    "LLM generate success | model=%s | time=%.2fs | prompt_len=%d | response_len=%d",
                    self.__model, time.monotonic() - start, len(prompt), len(content),
                )
                return content

        except asyncio.TimeoutError:
            logger.error(
                "LLM generate timeout | model=%s | timeout=%.1fs | prompt_len=%d",
                self.__model, timeout_seconds, len(prompt),
            )
            raise
        except Exception as e:
            logger.exception(
                "LLM generate unknown error | model=%s | prompt_len=%d",
                self.__model, len(prompt),
            )
            raise

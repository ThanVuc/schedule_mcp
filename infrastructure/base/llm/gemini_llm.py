import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from aio_pika import logger
import aiohttp
from application.dtos.common import FileDTO
from application.settings import LLMAgentSettings, LLMSettings
from infrastructure.base.const.infra_const import LLMAgentName, LLMModel


@dataclass(frozen=True)
class LLMAgentProfile:
    model: LLMModel
    top_p: float
    top_k: int
    temperature: float
    timeout_seconds: float


DEFAULT_AGENT_PROFILES: dict[LLMAgentName, LLMAgentProfile] = {
    LLMAgentName.EXTRACTION: LLMAgentProfile(
        model=LLMModel.GEMINI_3_1_FLASH_LITE,
        top_p=0.9,
        top_k=20,
        temperature=0.1,
        timeout_seconds=45.0,
    ),
    LLMAgentName.RECONCILIATION: LLMAgentProfile(
        model=LLMModel.GEMINI_2_5_PRO,
        top_p=0.85,
        top_k=40,
        temperature=0.2,
        timeout_seconds=60.0,
    ),
    LLMAgentName.TASK_GENERATION: LLMAgentProfile(
        model=LLMModel.GEMINI_3_0_FLASH,
        top_p=0.9,
        top_k=40,
        temperature=0.4,
        timeout_seconds=60.0,
    ),
}


class LLMConnector:
    _GENERATE_MAX_ATTEMPTS = 3
    _RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

    def __init__(self, llm_settings: LLMSettings):
        self.__api_key = llm_settings.api_key
        self.__model = LLMModel(llm_settings.model)
        self.__agent_profiles = self._build_agent_profiles(llm_settings)
        self.__session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.__api_key,
            },
            connector=aiohttp.TCPConnector(keepalive_timeout=300)
        )

    async def close(self) -> None:
        if not self.__session.closed:
            await self.__session.close()

    def _build_agent_profiles(self, llm_settings: LLMSettings) -> dict[LLMAgentName, LLMAgentProfile]:
        profiles = dict(DEFAULT_AGENT_PROFILES)
        custom_profiles = {
            LLMAgentName.EXTRACTION: llm_settings.extraction_agent,
            LLMAgentName.RECONCILIATION: llm_settings.reconciliation_agent,
            LLMAgentName.TASK_GENERATION: llm_settings.task_generation_agent,
        }
        for agent_name, custom_profile in custom_profiles.items():
            if custom_profile is None:
                continue
            profiles[agent_name] = self._convert_agent_settings(custom_profile)
        return profiles

    @staticmethod
    def _convert_agent_settings(agent_settings: LLMAgentSettings) -> LLMAgentProfile:
        return LLMAgentProfile(
            model=LLMModel(agent_settings.model),
            top_p=agent_settings.top_p,
            top_k=agent_settings.top_k,
            temperature=agent_settings.temperature,
            timeout_seconds=agent_settings.timeout_seconds,
        )

    @property
    def model(self) -> LLMModel:
        return self.__model

    def set_model(self, model: LLMModel | str) -> None:
        self.__model = LLMModel(model)

    def get_agent_profile(self, agent_name: LLMAgentName | str) -> LLMAgentProfile:
        resolved_agent_name = LLMAgentName(agent_name)
        return self.__agent_profiles[resolved_agent_name]

    def _resolve_model(self, model: Optional[LLMModel | str]) -> LLMModel:
        if model is None:
            return self.__model
        return LLMModel(model)

    def _build_generate_url(self, model: LLMModel) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model.value}:generateContent"

    async def generate(
        self,
        prompt: str,
        model: Optional[LLMModel | str] = None,
        fallback_models: Optional[list[LLMModel | str]] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        max_output_tokens: int = 1024,
        timeout_seconds: float = 60.0,
        afc_enabled: bool = False,
        files: Optional[list[FileDTO]] = None,
    ):
        primary_model = self._resolve_model(model)
        model_sequence = [primary_model]
        if fallback_models:
            for fallback_model in fallback_models:
                resolved_fallback = self._resolve_model(fallback_model)
                if resolved_fallback not in model_sequence:
                    model_sequence.append(resolved_fallback)

        # 1. Cấu hình Headers
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.__api_key,
        }

        # 2. Xây dựng Payload (bao gồm tắt AFC bằng mode: NONE)
        parts = [{"text": prompt}]
        if files:
            for file in files:
                parts.append({
                    "file_data": {
                        "mime_type": file.mime,
                        "file_uri": file.uri,
                    }
                })

        payload = {
            "contents": [
                {
                    "parts": parts
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

        for model_index, resolved_model in enumerate(model_sequence):
            generate_url = self._build_generate_url(resolved_model)
            backoff_seconds = 1.0

            for attempt in range(1, self._GENERATE_MAX_ATTEMPTS + 1):
                try:
                    start = time.monotonic()
                    async with self.__session.post(
                        generate_url,
                        json=payload,
                        headers=headers,
                        timeout=timeout
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data['candidates'][0]['content']['parts'][0]['text']
                            logger.info(
                                "LLM generate success | model=%s | time=%.2fs | prompt_len=%d | response_len=%d | attempt=%d",
                                resolved_model.value, time.monotonic() - start, len(prompt), len(content), attempt,
                            )
                            return content

                        error_body = await response.text()
                        is_retryable_status = response.status in self._RETRYABLE_STATUSES

                        if is_retryable_status and attempt < self._GENERATE_MAX_ATTEMPTS:
                            logger.warning(
                                "LLM generate transient status | model=%s | status=%d | attempt=%d/%d | retry_in=%.1fs",
                                resolved_model.value,
                                response.status,
                                attempt,
                                self._GENERATE_MAX_ATTEMPTS,
                                backoff_seconds,
                            )
                            await asyncio.sleep(backoff_seconds)
                            backoff_seconds *= 2
                            continue

                        logger.error(
                            "LLM generate error | model=%s | status=%d | prompt_len=%d | body=%s",
                            resolved_model.value,
                            response.status,
                            len(prompt),
                            error_body,
                        )

                        can_fallback = (
                            is_retryable_status
                            and model_index < len(model_sequence) - 1
                            and attempt == self._GENERATE_MAX_ATTEMPTS
                        )
                        if can_fallback:
                            logger.warning(
                                "LLM switching fallback model | from=%s | to=%s | status=%d",
                                resolved_model.value,
                                model_sequence[model_index + 1].value,
                                response.status,
                            )
                            break

                        raise Exception(f"LLM generate error with status code {response.status}")

                except (asyncio.TimeoutError, aiohttp.ServerDisconnectedError, aiohttp.ClientConnectionError, aiohttp.ClientOSError):
                    if attempt < self._GENERATE_MAX_ATTEMPTS:
                        logger.warning(
                            "LLM generate transient exception | model=%s | attempt=%d/%d | retry_in=%.1fs",
                            resolved_model.value,
                            attempt,
                            self._GENERATE_MAX_ATTEMPTS,
                            backoff_seconds,
                        )
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue

                    if model_index < len(model_sequence) - 1:
                        logger.warning(
                            "LLM switching fallback model after exception | from=%s | to=%s",
                            resolved_model.value,
                            model_sequence[model_index + 1].value,
                        )
                        break

                    logger.error(
                        "LLM generate timeout/disconnect | model=%s | timeout=%.1fs | prompt_len=%d | attempts=%d",
                        resolved_model.value,
                        timeout_seconds,
                        len(prompt),
                        self._GENERATE_MAX_ATTEMPTS,
                    )
                    raise
                except Exception:
                    logger.exception(
                        "LLM generate unknown error | model=%s | prompt_len=%d | attempt=%d",
                        resolved_model.value,
                        len(prompt),
                        attempt,
                    )
                    raise

        raise Exception("LLM generate failed after retries")

    async def generate_for_agent(
        self,
        prompt: str,
        agent_name: LLMAgentName | str,
        max_output_tokens: int = 1024,
        afc_enabled: bool = False,
        files: Optional[list[FileDTO]] = None,
    ):
        profile = self.get_agent_profile(agent_name)
        return await self.generate(
            prompt=prompt,
            model=profile.model,
            temperature=profile.temperature,
            top_p=profile.top_p,
            top_k=profile.top_k,
            timeout_seconds=profile.timeout_seconds,
            max_output_tokens=max_output_tokens,
            afc_enabled=afc_enabled,
            files=files,
        )

    async def upload_file(self, object_key: str, content: bytes, mime: str) -> FileDTO:
        if not self.__api_key:
            raise ValueError("Gemini API key is not set in LLM settings.")

        if not content:
            raise ValueError("File content is empty.")

        # Step 1: Start resumable upload session.
        start_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        start_headers = {
            "x-goog-api-key": self.__api_key,
            "Content-Type": "application/json",
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(content)),
            "X-Goog-Upload-Header-Content-Type": mime,
        }
        start_payload = {
            "file": {
                "displayName": object_key,
            }
        }

        async with self.__session.post(
            start_url,
            json=start_payload,
            headers=start_headers,
        ) as start_response:
            if start_response.status not in (200, 201):
                error_body = await start_response.text()
                logger.error(
                    "LLM file start upload error | status=%d | object_key=%s | body=%s",
                    start_response.status,
                    object_key,
                    error_body,
                )
                raise Exception(f"LLM file start upload error with status code {start_response.status}")

            upload_url = start_response.headers.get("X-Goog-Upload-URL")
            if not upload_url:
                error_body = await start_response.text()
                logger.error(
                    "LLM file start upload missing upload URL | object_key=%s | body=%s",
                    object_key,
                    error_body,
                )
                raise Exception("LLM file start upload missing upload URL")

        # Step 2: Upload bytes and finalize.
        upload_headers = {
            "x-goog-api-key": self.__api_key,
            "Content-Type": mime,
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        }

        async with self.__session.post(
            upload_url,
            data=content,
            headers=upload_headers,
        ) as upload_response:
            if upload_response.status not in (200, 201):
                error_body = await upload_response.text()
                logger.error(
                    "LLM file upload error | status=%d | object_key=%s | body=%s",
                    upload_response.status,
                    object_key,
                    error_body,
                )
                raise Exception(f"LLM file upload error with status code {upload_response.status}")

            upload_data = await upload_response.json()

        uploaded_file = upload_data.get("file", {})
        file_uri = uploaded_file.get("uri")
        uploaded_mime = uploaded_file.get("mimeType") or mime

        if not file_uri:
            logger.error(
                "LLM file upload missing file uri | object_key=%s | response=%s",
                object_key,
                upload_data,
            )
            raise Exception("LLM file upload response missing file uri")

        logger.info(
            "LLM file upload success | object_key=%s | uri=%s | mime=%s",
            object_key,
            file_uri,
            uploaded_mime,
        )

        return FileDTO(mime=uploaded_mime, uri=file_uri, name=object_key)

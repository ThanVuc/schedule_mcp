# setup storage for R2 Object Storage
import mimetypes
import logging

import aioboto3
from botocore.config import Config
from application.settings import StorageSettings
from infrastructure.base.const.infra_const import R2_ENDPOINT_TEMPLATE, StorageProvider

try:
    import magic
except ImportError:
    magic = None


class Storage:
    def __init__(self, storage_settings: StorageSettings):
        self.account_id = storage_settings.account_id
        self.provider = StorageProvider(storage_settings.provider)
        self.endpoint = storage_settings.endpoint or R2_ENDPOINT_TEMPLATE.format(account_id=self.account_id)
        self.access_key_id = storage_settings.access_key_id
        self.secret_access_key = storage_settings.secret_access_key
        self.bucket = storage_settings.bucket
        self.use_ssl = storage_settings.use_ssl
        self._session = aioboto3.Session()
        self._client_config = Config(
            connect_timeout=storage_settings.connect_timeout_seconds,
            read_timeout=storage_settings.read_timeout_seconds,
            retries={"max_attempts": storage_settings.max_retries, "mode": "standard"},
        )

    async def download_with_robust_mime(self, object_key: str) -> tuple[bytes, str]:
        try:
            async with self._session.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                use_ssl=self.use_ssl,
                region_name="auto",
                config=self._client_config,
            ) as client:
                response = await client.get_object(
                    Bucket=self.bucket,
                    Key=object_key,
                )
                data = await response["Body"].read()
        except Exception as exc:
            logging.exception(
                "storage download failed | bucket=%s | key=%s | endpoint=%s",
                self.bucket,
                object_key,
                self.endpoint,
            )
            raise RuntimeError(f"Failed to download object '{object_key}' from storage") from exc

        # 1. Detect MIME directly from bytes when libmagic is available.
        content_type = ""
        if magic is not None:
            try:
                content_type = magic.from_buffer(data, mime=True) or ""
            except Exception:
                content_type = ""

        # 2. Fallback: MIME type from object metadata
        if not content_type:
            content_type = response.get("ContentType", "")

        # 3. Fallback: guess from filename
        ext = ""
        if not content_type:
            content_type, _ = mimetypes.guess_type(object_key)

        if not content_type:
            content_type = "application/octet-stream"

        # 4. Extract extension
        ext = object_key.split(".")[-1].lower() if "." in object_key else ""

        return data, content_type

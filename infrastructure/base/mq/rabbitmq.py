import aio_pika
import asyncio
from typing import Optional

from application.settings import MQSettings


class RabbitMQConnector:
    _instance: Optional["RabbitMQConnector"] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        mq_settings: MQSettings,
        shared_prefetch: int = 10,
    ):
        if hasattr(self, "_initialized"):
            return
        
        mq_url = f"amqp://{mq_settings.user}:{mq_settings.password}@{mq_settings.host}:{mq_settings.port}/"

        self.amqp_url = mq_url
        self.shared_prefetch = shared_prefetch

        self._connection: Optional[aio_pika.RobustConnection] = None
        self._shared_channel: Optional[aio_pika.RobustChannel] = None

        self._initialized = True

    async def connect(self) -> None:
        if self._connection and not self._connection.is_closed:
            return

        async with self._lock:
            if self._connection and not self._connection.is_closed:
                return

            self._connection = await aio_pika.connect_robust(self.amqp_url)

    async def get_shared_channel(self) -> aio_pika.RobustChannel:
        await self.connect()

        if self._shared_channel and not self._shared_channel.is_closed:
            return self._shared_channel

        async with self._lock:
            if self._shared_channel and not self._shared_channel.is_closed:
                return self._shared_channel

            self._shared_channel = await self._connection.channel()
            await self._shared_channel.set_qos(
                prefetch_count=self.shared_prefetch
            )

            return self._shared_channel

    async def get_channel(
        self,
        prefetch: Optional[int] = None,
    ) -> aio_pika.RobustChannel:
        await self.connect()

        channel = await self._connection.channel()

        if prefetch is not None:
            await channel.set_qos(prefetch_count=prefetch)

        return channel

    async def close(self) -> None:
        async with self._lock:
            if self._shared_channel and not self._shared_channel.is_closed:
                await self._shared_channel.close()

            if self._connection and not self._connection.is_closed:
                await self._connection.close()

            self._shared_channel = None
            self._connection = None

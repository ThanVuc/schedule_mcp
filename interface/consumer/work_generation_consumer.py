import asyncio
import contextlib
import logging

from aio_pika import ExchangeType, IncomingMessage
from aio_pika.abc import AbstractRobustQueue, AbstractRobustExchange
from application.dtos.work_generation_dto import WorkGenerationMessageDTO
from application.publisher.notification_publisher import NotificationPublisher
from application.usecase.work_generation_usecase import WorkGenerationUseCase
from constant.mq import WORK_GENERATION_EXCHANGE, WORK_GENERATION_QUEUE, WORK_GENERATION_ROUTING_KEY, WORK_TRANSFER_ROUTING_KEY
from domain.entities.notification_entity import Notification
from infrastructure.base.mq.rabbitmq import RabbitMQConnector
from interface.consumer.base import Runnable

logger = logging.getLogger(__name__)

class WorkGenerationConsumer(Runnable):
    def __init__(
        self,
        mq_connector: RabbitMQConnector,
        work_generation_usecase: WorkGenerationUseCase,
        notification_publisher: NotificationPublisher,
        *,
        concurrency: int = 10,
    ):
        self.mq_connector = mq_connector
        self.work_generation_usecase = work_generation_usecase
        self.notification_publisher = notification_publisher

        self._concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)

        self._running = False
        self._consume_task: asyncio.Task | None = None
        self._worker_tasks: set[asyncio.Task] = set()

    async def run(self):
        if self._running:
            return
        self._running = True
        self._consume_task = asyncio.create_task(self._consume())
        logger.info("WorkGenerationConsumer started | concurrency=%d", self._concurrency)

    async def stop(self):
        logger.info("Stopping WorkGenerationConsumer...")
        self._running = False

        if self._consume_task:
            self._consume_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consume_task

        if self._worker_tasks:
            logger.info("Waiting %d in-flight tasks...", len(self._worker_tasks))
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        logger.info("WorkGenerationConsumer stopped")

    async def _consume(self):
        queue = await WorkGenerationConsumer.create_work_generation_queue(
            self.mq_connector,
            concurrency=self._concurrency,
        )

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._running:
                    break

                task = asyncio.create_task(self._handle_message(
                    message
                ))
                self._worker_tasks.add(task)
                task.add_done_callback(self._worker_tasks.discard)

    async def _handle_message(self, message: IncomingMessage,):
        async with self._semaphore:
            try:
                dto = WorkGenerationMessageDTO.model_validate_json(message.body)
                message_id = message.message_id or message.headers.get("request_id", "")

                logger.info(
                    "Processing work generation | message_id=%s",
                    message_id,
                )

                await self.work_generation_usecase.generate_work(dto, message_id)

                await message.ack()

            except asyncio.CancelledError:
                # Shutdown → trả message lại queue
                await message.nack(requeue=True)
                raise

            except Exception:
                logger.exception(
                    "Failed to process message | message_id=%s",
                    message.message_id,
                )

                user_id = getattr(dto, "user_id", None)

                if user_id:
                    await self.notification_publisher.publish(
                        Notification(
                            title="Tạo công việc với AI thất bại",
                            message="Hệ thống gặp lỗi khi tạo công việc cho bạn. Vui lòng thử lại sau.",
                            sender_id="system",
                            receiver_ids=[dto.user_id],
                            correlation_id=message.message_id,
                            correlation_type=2,
                        )
                    )

                await message.nack(requeue=False)

    async def create_work_generation_queue(
        mq_connector: RabbitMQConnector,
        *,
        concurrency: int = 10,
    ) -> AbstractRobustQueue:
        channel = await mq_connector.get_channel()
        await channel.set_qos(prefetch_count=concurrency)

        exchange = await channel.declare_exchange(
            WORK_GENERATION_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )

        queue = await channel.declare_queue(
            WORK_GENERATION_QUEUE,
            durable=True,
        )

        await queue.bind(exchange, WORK_GENERATION_ROUTING_KEY)
        return queue

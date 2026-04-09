import asyncio
import contextlib
import logging

from aio_pika import ExchangeType, IncomingMessage
from aio_pika.abc import AbstractRobustQueue

from application.dtos.sprint_generation_dto import AISprintGenerationRequestedMessageDTO
from application.usecase.sprint_generation_usecase import SprintGenerationUseCase
from constant.mq import (
	AI_TEAM_EXCHANGE,
	AI_TEAM_SPRINT_GENERATION_QUEUE,
	AI_TEAM_SPRINT_GENERATION_ROUTING_KEY,
)
from infrastructure.base.mq.rabbitmq import RabbitMQConnector
from interface.consumer.base import Runnable

logger = logging.getLogger(__name__)


class SprintGenerationConsumer(Runnable):
	def __init__(
		self,
		mq_connector: RabbitMQConnector,
		sprint_generation_usecase: SprintGenerationUseCase,
		*,
		concurrency: int = 10,
	):
		self.mq_connector = mq_connector
		self.sprint_generation_usecase = sprint_generation_usecase

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
		logger.info("SprintGenerationConsumer started | concurrency=%d", self._concurrency)

	async def stop(self):
		logger.info("Stopping SprintGenerationConsumer...")
		self._running = False

		if self._consume_task:
			self._consume_task.cancel()
			with contextlib.suppress(asyncio.CancelledError):
				await self._consume_task

		if self._worker_tasks:
			logger.info("Waiting %d in-flight sprint tasks...", len(self._worker_tasks))
			await asyncio.gather(*self._worker_tasks, return_exceptions=True)

		logger.info("SprintGenerationConsumer stopped")

	async def _consume(self):
		queue = await SprintGenerationConsumer.create_sprint_generation_queue(
			self.mq_connector,
			concurrency=self._concurrency,
		)

		async with queue.iterator() as queue_iter:
			async for message in queue_iter:
				if not self._running:
					break

				task = asyncio.create_task(self._handle_message(message))
				self._worker_tasks.add(task)
				task.add_done_callback(self._worker_tasks.discard)

	async def _handle_message(self, message: IncomingMessage):
		async with self._semaphore:
			try:
				dto = AISprintGenerationRequestedMessageDTO.model_validate_json(message.body)
				await self.sprint_generation_usecase.process_sprint_generation_request(dto)
				await message.ack()
			except asyncio.CancelledError:
				await message.nack(requeue=True)
				raise
			except Exception:
				logger.exception(
					"failed to process sprint generation request | message_id=%s",
					message.message_id,
				)
				await message.nack(requeue=False)

	async def create_sprint_generation_queue(
		mq_connector: RabbitMQConnector,
		*,
		concurrency: int = 10,
	) -> AbstractRobustQueue:
		channel = await mq_connector.get_channel()
		await channel.set_qos(prefetch_count=concurrency)

		exchange = await channel.declare_exchange(
			AI_TEAM_EXCHANGE,
			ExchangeType.DIRECT,
			durable=True,
		)

		queue = await channel.declare_queue(
			AI_TEAM_SPRINT_GENERATION_QUEUE,
			durable=True,
		)

		await queue.bind(exchange, AI_TEAM_SPRINT_GENERATION_ROUTING_KEY)
		return queue

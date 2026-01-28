import asyncio

from aio_pika import ExchangeType, Message
from constant.mq import WORK_GENERATION_EXCHANGE, WORK_GENERATION_QUEUE, WORK_GENERATION_ROUTING_KEY, WORK_TRANSFER_EXCHANGE, WORK_TRANSFER_QUEUE, WORK_TRANSFER_ROUTING_KEY
from infrastructure.base.mq.rabbitmq import RabbitMQConnector
from interface.consumer.base import Runnable


class WorkGenerationConsumer(Runnable):
    def __init__(self, mq_connector: RabbitMQConnector):
        self.mq_connector = mq_connector
        self._task = None
        self._running = True

    async def run(self):
        self._task = asyncio.create_task(self._consume())

    async def _consume(self):
        channel = await self.mq_connector.get_channel()
        shared_channel = await self.mq_connector.get_shared_channel()

        exchange = await channel.declare_exchange(
            name=WORK_GENERATION_EXCHANGE,
            type= ExchangeType.DIRECT, 
            durable=True
        )

        publisher_exchange = await shared_channel.declare_exchange(
            name=WORK_TRANSFER_EXCHANGE,
            type= ExchangeType.DIRECT,  
            durable=True
        )

        queue = await channel.declare_queue(
            name=WORK_GENERATION_QUEUE,
            durable=True
        )

        publicher_queue = await shared_channel.declare_queue(
            name=WORK_TRANSFER_QUEUE,
            durable=True,
        )

        await queue.bind(exchange, routing_key=WORK_GENERATION_ROUTING_KEY)
        await publicher_queue.bind(publisher_exchange, routing_key=WORK_TRANSFER_ROUTING_KEY)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._running:
                    break
                async with message.process():
                    outgoing = Message(
                        body=message.body,
                        headers=message.headers,
                        delivery_mode=message.delivery_mode,
                    )

                    # Xử lý tin nhắn ở đây
                    print(f"Received message: {message.body.decode()}")
                    # Ví dụ: Chuyển tiếp tin nhắn đến hàng đợi khác
                    await publisher_exchange.publish(
                        outgoing,
                        routing_key=WORK_TRANSFER_ROUTING_KEY
                    )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

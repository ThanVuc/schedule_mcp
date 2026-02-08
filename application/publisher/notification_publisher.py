import json
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractRobustExchange

from constant.mq import NOTIFICATION_GENERATE_WORK_EXCHANGE, NOTIFICATION_GENERATE_WORK_ROUTING_KEY
from domain.entities.notification_entity import Notification
from infrastructure.base.mq.rabbitmq import RabbitMQConnector

class NotificationPublisher:
    def __init__(self, exchange: AbstractRobustExchange):
        self.exchange = exchange

    @classmethod
    async def create(cls, mq_connector: RabbitMQConnector):
        channel = await mq_connector.get_shared_channel()
        exchange = await channel.declare_exchange(
            NOTIFICATION_GENERATE_WORK_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )
        return cls(exchange)

    async def publish(self, notification: Notification):
        body = json.dumps(notification.__dict__).encode()
        await self.exchange.publish(
            Message(
                body=body,
                content_type="application/json",
            ),
            routing_key=NOTIFICATION_GENERATE_WORK_ROUTING_KEY,
        )

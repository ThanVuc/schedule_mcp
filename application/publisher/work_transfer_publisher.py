import json
from typing import List
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractRobustExchange
from application.dtos.work_generation_dto import WorkGenerationMessageDTO
from constant.mq import WORK_TRANSFER_EXCHANGE, WORK_TRANSFER_ROUTING_KEY
from domain.entities.notification_entity import Notification
from domain.entities.work_entity import Work
from infrastructure.base.mq.rabbitmq import RabbitMQConnector
from dataclasses import asdict

class WorkTransferPublisher:
    def __init__(self, exchange: AbstractRobustExchange):
        self.exchange = exchange

    @classmethod
    async def create(cls, mq_connector: RabbitMQConnector):
        channel = await mq_connector.get_shared_channel()
        exchange = await channel.declare_exchange(
            WORK_TRANSFER_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )
        return cls(exchange)

    async def publish(self, works: List[Work], dto: WorkGenerationMessageDTO, message_id: str):
        body = json.dumps(
            [asdict(work) for work in works]
        ).encode()

        await self.exchange.publish(
            Message(
                headers={"user_id": dto.user_id, "message_id": message_id},
                body=body,
                content_type="application/json",
                delivery_mode=2,
            ),
            routing_key=WORK_TRANSFER_ROUTING_KEY,
        )

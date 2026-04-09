import json

from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractRobustExchange

from application.dtos.sprint_generation_dto import AISprintGenerationResultMessageDTO
from constant.mq import TEAM_AI_EXCHANGE, TEAM_AI_SPRINT_GENERATION_RESULT_ROUTING_KEY
from infrastructure.base.mq.rabbitmq import RabbitMQConnector


class SprintResultPublisher:
    def __init__(self, exchange: AbstractRobustExchange):
        self.exchange = exchange

    @classmethod
    async def create(cls, mq_connector: RabbitMQConnector):
        channel = await mq_connector.get_shared_channel()
        exchange = await channel.declare_exchange(
            TEAM_AI_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )
        return cls(exchange)

    async def publish(self, message: AISprintGenerationResultMessageDTO):
        body = json.dumps(message.model_dump(mode="json", exclude_none=True)).encode()
        await self.exchange.publish(
            Message(
                body=body,
                content_type="application/json",
                delivery_mode=2,
            ),
            routing_key=TEAM_AI_SPRINT_GENERATION_RESULT_ROUTING_KEY,
        )

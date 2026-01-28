from application.settings import MQSettings
from infrastructure.base.mq.rabbitmq import RabbitMQConnector


class MQContainer:
    def __init__(self, mq_settings: MQSettings):
        self.mq_connector = RabbitMQConnector(mq_settings=mq_settings)

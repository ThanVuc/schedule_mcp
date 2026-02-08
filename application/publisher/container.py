from application.publisher.notification_publisher import NotificationPublisher
from application.publisher.work_transfer_publisher import WorkTransferPublisher
from infrastructure.base.mq.rabbitmq import RabbitMQConnector


class PublisherContainer:
    def __init__(self):
        self.notification_publisher: NotificationPublisher | None = None
        self.work_transfer_publisher: WorkTransferPublisher | None = None

    async def init(self, mq_connector: RabbitMQConnector):
        self.notification_publisher = await NotificationPublisher.create(mq_connector)
        self.work_transfer_publisher = await WorkTransferPublisher.create(mq_connector)

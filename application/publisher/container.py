from application.publisher.notification_publisher import NotificationPublisher
from application.publisher.sprint_result_publisher import SprintResultPublisher
from application.publisher.team_notification_publisher import TeamNotificationPublisher
from application.publisher.work_transfer_publisher import WorkTransferPublisher
from infrastructure.base.mq.rabbitmq import RabbitMQConnector


class PublisherContainer:
    def __init__(self):
        self.notification_publisher: NotificationPublisher | None = None
        self.team_notification_publisher: TeamNotificationPublisher | None = None
        self.work_transfer_publisher: WorkTransferPublisher | None = None
        self.sprint_result_publisher: SprintResultPublisher | None = None

    async def init(self, mq_connector: RabbitMQConnector):
        self.notification_publisher = await NotificationPublisher.create(mq_connector)
        self.team_notification_publisher = await TeamNotificationPublisher.create(mq_connector)
        self.work_transfer_publisher = await WorkTransferPublisher.create(mq_connector)
        self.sprint_result_publisher = await SprintResultPublisher.create(mq_connector)

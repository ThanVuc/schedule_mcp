from .database import DatabaseContainer
from .configuration import InitSettings


class BaseInfrastructureContainer:
    def __init__(self):
        self.settings = InitSettings()
        self.database = DatabaseContainer(settings=self.settings)

from infrastructure.base.configuration import Settings
from .qdrant import QdrantClient
from .redis import RedisClient
from .sqlite import SqliteClient


class DatabaseContainer:
    def __init__(self, settings: Settings):
        self.qdrant = QdrantClient(settings=settings)
        self.redis = RedisClient(settings=settings)
        self.sqlite = SqliteClient(settings=settings)

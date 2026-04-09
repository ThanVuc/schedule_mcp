
from pydantic import BaseModel


class FileDTO(BaseModel):
    mime: str
    uri: str
    name: str

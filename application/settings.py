from pydantic_settings import BaseSettings
from pydantic import BaseModel

# --- Subsystem configs ---
class MQSettings(BaseModel):
    host: str
    port: int
    user: str
    password: str

class LLMSettings(BaseModel):
    api_key: str
    model: str

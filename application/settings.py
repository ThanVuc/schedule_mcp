from pydantic_settings import BaseSettings
from pydantic import BaseModel
import yaml

# --- Subsystem configs ---
class DatabaseSettings(BaseModel):
    sqlite_url: str
    redis_host: str
    redis_port: int
    qdrant_url: str

class MQSettings(BaseModel):
    rabbitmq_url: str

class LLMSettings(BaseModel):
    custom_llm_model: str
    gemini_llm_model: str

class EmbedderSettings(BaseModel):
    openai_api_key: str

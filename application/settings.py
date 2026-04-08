from pydantic_settings import BaseSettings
from pydantic import BaseModel

# --- Subsystem configs ---
class MQSettings(BaseModel):
    host: str
    port: int
    user: str
    password: str

class LLMAgentSettings(BaseModel):
    model: str
    top_p: float
    top_k: int
    temperature: float
    timeout_seconds: float


class LLMSettings(BaseModel):
    api_key: str
    model: str
    extraction_agent: LLMAgentSettings | None = None
    reconciliation_agent: LLMAgentSettings | None = None
    task_generation_agent: LLMAgentSettings | None = None

class EmbedderSettings(BaseModel):
    model_name: str
    download_timeout_seconds: float = 60

class StorageSettings(BaseModel):
    provider: str = "r2"
    account_id: str
    endpoint: str = ""
    access_key_id: str
    secret_access_key: str
    bucket: str
    use_ssl: bool = True
    connect_timeout_seconds: float = 10
    read_timeout_seconds: float = 30
    max_retries: int = 2

class AppSettings(BaseSettings):
    env: str
    mq: MQSettings
    llm: LLMSettings
    embedder: EmbedderSettings
    storage: StorageSettings

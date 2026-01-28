from pydantic_settings import BaseSettings
import yaml

from application.settings import LLMSettings, MQSettings

class Settings(BaseSettings):
    env: str
    mq: MQSettings
    llm: LLMSettings

    @classmethod
    def from_yaml(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)

def InitSettings() -> Settings:
    return Settings.from_yaml("configs/settings.yaml")

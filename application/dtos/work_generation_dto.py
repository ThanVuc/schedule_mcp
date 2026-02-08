from pydantic import BaseModel
from typing import Optional

class WorkGenerationMessageDTO(BaseModel):
    user_id: str
    prompts: str
    local_date: str
    additional_context: Optional[str]
    constraints: Optional[str]
    user_personality: Optional[str]

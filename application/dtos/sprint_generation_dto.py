from typing import Optional

from pydantic import BaseModel, Field


class AISprintGenerationFileDTO(BaseModel):
    object_key: str
    size: int


class AISprintGenerationSprintDTO(BaseModel):
    name: str
    goal: Optional[str] = None
    start_date: str
    end_date: str


class AISprintGenerationRequestedPayloadDTO(BaseModel):
    sprint: AISprintGenerationSprintDTO
    files: list[AISprintGenerationFileDTO] = Field(default_factory=list)
    additional_context: Optional[str] = None


class AISprintGenerationRequestedMessageDTO(BaseModel):
    event_type: str
    job_id: str
    group_id: str
    sender_id: str
    payload: AISprintGenerationRequestedPayloadDTO


class AISprintGenerationResultTaskDTO(BaseModel):
    name: str
    description: str
    priority: Optional[str] = None
    story_point: Optional[int] = None
    due_date: Optional[str] = None


class AISprintGenerationResultErrorDTO(BaseModel):
    code: Optional[str] = None
    message: Optional[str] = None
    detail: Optional[str] = None


class AISprintGenerationResultPayloadDTO(BaseModel):
    status: str
    sprint: AISprintGenerationSprintDTO
    tasks: list[AISprintGenerationResultTaskDTO] = Field(default_factory=list)
    error: Optional[AISprintGenerationResultErrorDTO] = None


class AISprintGenerationResultMessageDTO(BaseModel):
    event_type: str
    job_id: str
    group_id: str
    sender_id: str
    payload: AISprintGenerationResultPayloadDTO


class TeamNotificationPayloadDTO(BaseModel):
    title: str
    message: str
    correlation_id: str
    correlation_type: int
    link: Optional[str] = None
    img_url: Optional[str] = None


class TeamNotificationMetadataDTO(BaseModel):
    is_send_mail: bool = False


class TeamNotificationMessageDTO(BaseModel):
    event_type: str
    sender_id: str
    receiver_ids: list[str] = Field(default_factory=list)
    payload: TeamNotificationPayloadDTO
    metadata: TeamNotificationMetadataDTO = Field(default_factory=TeamNotificationMetadataDTO)

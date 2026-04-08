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

class FeatureDTO(BaseModel):
    title: str
    description: str | None = None

class TaskDTO(BaseModel):
    title: str
    description: str | None = None
    related_feature: str | None = None

class UserFlowDTO(BaseModel):
    name: str
    steps: list[str] = Field(default_factory=list)

class ApiDTO(BaseModel):
    name: str
    endpoint: str | None = None
    method: str | None = None
    description: str | None = None

class ColumnDTO(BaseModel):
    name: str
    type: str | None = None
    constraints: list[str] = Field(default_factory=list)

class DbTableDTO(BaseModel):
    table: str
    columns: list[ColumnDTO] = Field(default_factory=list)

class ClassificationResultDTO(BaseModel):
    file_name: str
    type: str
    features: list[FeatureDTO] = Field(default_factory=list)
    tasks: list[TaskDTO] = Field(default_factory=list)
    user_flows: list[UserFlowDTO] = Field(default_factory=list)
    apis: list[ApiDTO] = Field(default_factory=list)
    db_schema: list[DbTableDTO] = Field(default_factory=list)

class NormalizationContentDTO(BaseModel):
    title: str
    description: str | None = None

class NormalizationSourceDTO(BaseModel):
    file_name: str
    type: str

class NormalizedItemDTO(BaseModel):
    id: str
    type: str
    content: NormalizationContentDTO
    source: NormalizationSourceDTO
    embedding: Optional[list[float]] = None
    cluster_id: Optional[str] = None

class NormalizationResultDTO(BaseModel):
    features: list[NormalizedItemDTO] = Field(default_factory=list)
    tasks: list[NormalizedItemDTO] = Field(default_factory=list)
    user_flows: list[NormalizedItemDTO] = Field(default_factory=list)
    apis: list[NormalizedItemDTO] = Field(default_factory=list)
    db_schemas: list[NormalizedItemDTO] = Field(default_factory=list)

class MergedItemDTO(BaseModel):
    id: str
    type: str
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    sources: list[NormalizationSourceDTO]
    cluster_id: Optional[str] = None

class ReconciliationResultDTO(BaseModel):
    features: list[MergedItemDTO] = Field(default_factory=list)
    tasks: list[MergedItemDTO] = Field(default_factory=list)
    user_flows: list[MergedItemDTO] = Field(default_factory=list)
    apis: list[MergedItemDTO] = Field(default_factory=list)
    db_schemas: list[MergedItemDTO] = Field(default_factory=list)

class CanonicalizationItemDTO(BaseModel):
    id: str
    type: str
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    sources: list[NormalizationSourceDTO]
    cluster_id: Optional[str] = None

class CanonicalizationFeatureDTO(CanonicalizationItemDTO):
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    tasks: list[CanonicalizationItemDTO] = Field(default_factory=list)
    user_flows: list[CanonicalizationItemDTO] = Field(default_factory=list)
    apis: list[CanonicalizationItemDTO] = Field(default_factory=list)
    db_schemas: list[CanonicalizationItemDTO] = Field(default_factory=list)
    cluster_id: Optional[str] = None

class CanonicalizationResultDTO(BaseModel):
    features: list[CanonicalizationFeatureDTO] = Field(default_factory=list)
    tasks: list[CanonicalizationItemDTO] = Field(default_factory=list) # orphan
    user_flows: list[CanonicalizationItemDTO] = Field(default_factory=list) # orphan
    apis: list[CanonicalizationItemDTO] = Field(default_factory=list) # orphan
    db_schemas: list[CanonicalizationItemDTO] = Field(default_factory=list) # orphan

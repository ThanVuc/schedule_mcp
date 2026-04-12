from typing import Any, Optional

from pydantic import BaseModel, Field

from application.const.sprint_generation import SignalOrigin, SignalType, SourceFileType, TaskPriority


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
    source_file_name: str
    source_file_type: SourceFileType
    signal_origin: SignalOrigin
    priority: Optional[str] = None
    story_point: Optional[int] = None
    due_date: Optional[str] = None


class CoverageIssueDTO(BaseModel):
    issue_id: str
    level: str
    issue_type: str
    signal_ref: Optional[dict[str, Any]] = None
    task_ref: Optional[dict[str, Any]] = None
    message: str


class CoverageSummaryDTO(BaseModel):
    primary_total: int
    covered_total: int
    primary_coverage_ratio: float
    error_count: int
    warning_count: int
    duplicate_intent_count: int
    weak_task_count: int


class TaskCriticalContextDTO(BaseModel):
    primary_signal_type: str
    primary_items: list[dict[str, Any]] = Field(default_factory=list)
    generated_tasks: list[AISprintGenerationResultTaskDTO] = Field(default_factory=list)
    issues: list[CoverageIssueDTO] = Field(default_factory=list)
    coverage_summary: CoverageSummaryDTO
    regenerate_budget: int


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


class IngestionInputFileDTO(BaseModel):
    object_key: str
    size: int


class MarkdownFileDTO(BaseModel):
    file_name: str
    object_key: str
    size: int
    content: bytes | None = None


class IngestionInputDTO(BaseModel):
    files: list[IngestionInputFileDTO] = Field(default_factory=list)


class IngestionOutputDTO(BaseModel):
    files: list[MarkdownFileDTO] = Field(default_factory=list)


class ExtractionInputDTO(BaseModel):
    files: list[MarkdownFileDTO] = Field(default_factory=list)

class NormalizationContentDTO(BaseModel):
    title: str
    description: str | None = None


class NormalizationSourceDTO(BaseModel):
    file_name: str
    type: str


class NormalizedItemDTO(BaseModel):
    id: str
    type: str
    signal_origin: SignalOrigin = SignalOrigin.EXPLICIT
    content: NormalizationContentDTO
    source_file_name: str
    source_file_type: SourceFileType
    embedding: Optional[list[float]] = None
    cluster_id: Optional[str] = None

class NormalizationResultDTO(BaseModel):
    features: list[NormalizedItemDTO] = Field(default_factory=list)
    tasks: list[NormalizedItemDTO] = Field(default_factory=list)
    apis: list[NormalizedItemDTO] = Field(default_factory=list)
    database: list[NormalizedItemDTO] = Field(default_factory=list)


class MergedItemDTO(BaseModel):
    id: str
    type: str
    signal_origin: SignalOrigin = SignalOrigin.EXPLICIT
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_file_name: str
    source_file_type: SourceFileType
    cluster_id: Optional[str] = None


class ReconciliationOutputDTO(BaseModel):
    features: list[MergedItemDTO] = Field(default_factory=list)
    tasks: list[MergedItemDTO] = Field(default_factory=list)
    apis: list[MergedItemDTO] = Field(default_factory=list)
    database: list[MergedItemDTO] = Field(default_factory=list)


class CanonicalizationItemDTO(BaseModel):
    id: str
    type: str
    signal_origin: SignalOrigin = SignalOrigin.EXPLICIT
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_file_name: str
    source_file_type: SourceFileType
    cluster_id: Optional[str] = None


class CanonicalizationFeatureDTO(CanonicalizationItemDTO):
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    tasks: list[CanonicalizationItemDTO] = Field(default_factory=list)
    apis: list[CanonicalizationItemDTO] = Field(default_factory=list)
    database: list[CanonicalizationItemDTO] = Field(default_factory=list)
    cluster_id: Optional[str] = None


class CanonicalizationResultDTO(BaseModel):
    features: list[CanonicalizationFeatureDTO] = Field(default_factory=list)
    tasks: list[CanonicalizationItemDTO] = Field(default_factory=list)
    apis: list[CanonicalizationItemDTO] = Field(default_factory=list)
    database: list[CanonicalizationItemDTO] = Field(default_factory=list)


# LLD-aligned DTOs (reused where possible)
IngestionFileDTO = IngestionInputFileDTO
SprintTaskDTO = AISprintGenerationResultTaskDTO
NormalizedSignalContentDTO = NormalizationContentDTO


class IngestionModelDTO(BaseModel):
    files: list[IngestionFileDTO] = Field(default_factory=list)


class SignalItemDTO(BaseModel):
    item_id: str
    signal_type: SignalType
    signal_origin: SignalOrigin = SignalOrigin.EXPLICIT
    title: str
    description: str | None = None
    source_file_name: str
    source_file_type: SourceFileType
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionModelDTO(BaseModel):
    api: list[SignalItemDTO] = Field(default_factory=list)
    databases: list[SignalItemDTO] = Field(default_factory=list)
    tasks: list[SignalItemDTO] = Field(default_factory=list)
    features: list[SignalItemDTO] = Field(default_factory=list)


class NormalizedSignalSourceDTO(BaseModel):
    file_name: str
    file_type: SourceFileType


class NormalizedSignalItemDTO(BaseModel):
    item_id: str
    signal_type: SignalType
    signal_origin: SignalOrigin = SignalOrigin.EXPLICIT
    content: NormalizedSignalContentDTO
    source: NormalizedSignalSourceDTO
    embedding: list[float] | None = None
    cluster_id: str | None = None


class NormalizationOutputDTO(BaseModel):
    api: list[NormalizedSignalItemDTO] = Field(default_factory=list)
    databases: list[NormalizedSignalItemDTO] = Field(default_factory=list)
    tasks: list[NormalizedSignalItemDTO] = Field(default_factory=list)
    features: list[NormalizedSignalItemDTO] = Field(default_factory=list)


class MergeItemDTO(BaseModel):
    canonical_id: str
    signal_type: SignalType
    signal_origin: SignalOrigin = SignalOrigin.EXPLICIT
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source: list[NormalizedSignalSourceDTO] = Field(default_factory=list)
    cluster_id: str | None = None


class ReconciliationModelDTO(BaseModel):
    api: list[MergeItemDTO] = Field(default_factory=list)
    databases: list[MergeItemDTO] = Field(default_factory=list)
    tasks: list[MergeItemDTO] = Field(default_factory=list)
    features: list[MergeItemDTO] = Field(default_factory=list)


class CanonicalItemDTO(BaseModel):
    canonical_id: str
    signal_type: SignalType
    signal_origin: SignalOrigin = SignalOrigin.EXPLICIT
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source: list[NormalizedSignalSourceDTO] = Field(default_factory=list)


class CanonicalFeatureDTO(BaseModel):
    feature_id: str
    title: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    related_items: list[CanonicalItemDTO] = Field(default_factory=list)


class CanonicalModelOutputDTO(BaseModel):
    apis: list[CanonicalItemDTO] = Field(default_factory=list)
    db_schema: list[CanonicalItemDTO] = Field(default_factory=list)
    tasks: list[CanonicalItemDTO] = Field(default_factory=list)
    features: list[CanonicalFeatureDTO] = Field(default_factory=list)


class TaskGenerationOutputDTO(BaseModel):
    tasks: list[SprintTaskDTO] = Field(default_factory=list)


class StrictSprintTaskDTO(BaseModel):
    name: str
    description: str
    source_file_name: str
    source_file_type: SourceFileType
    signal_origin: SignalOrigin
    priority: TaskPriority | None = None
    story_point: int | None = None
    due_date: str | None = None

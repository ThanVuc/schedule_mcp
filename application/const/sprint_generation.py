from __future__ import annotations

from enum import Enum


# Evidence step names and default output files.
STEP_INGESTION = "ingestion"
STEP_CLASSIFY_AND_EXTRACT = "classify_and_extract"
STEP_NORMALIZATION = "normalization"
STEP_RECONCILIATION = "reconciliation"
STEP_CANONICALIZATION = "canonicalization"
STEP_TASK_GENERATION = "task_generation"

EVIDENCE_FILE_BY_STEP: dict[str, str] = {
	STEP_INGESTION: "files.json",
	STEP_CLASSIFY_AND_EXTRACT: "classifications.json",
	STEP_NORMALIZATION: "normalized.json",
	STEP_RECONCILIATION: "reconciled.json",
	STEP_CANONICALIZATION: "canonicalized.json",
	STEP_TASK_GENERATION: "tasks.json",
}


# Classification type mapping by source-file prefix.
TYPE_BY_PREFIX: dict[str, str] = {
	"design": "Design",
	"planning": "Planning",
	"requirement": "Requirement",
}


# Extraction collection keys used for sparse-output detection.
EXTRACTION_COLLECTION_KEYS = (
	"features",
	"tasks",
	"apis",
	"db_schema",
)


class SourceFileType(str, Enum):
	PLANNING = "Planning"
	REQUIREMENT = "Requirement"
	DESIGN = "Design"


class SignalType(str, Enum):
	TASK = "task"
	API = "api"
	DATABASE = "database"
	FEATURE = "feature"


class SignalOrigin(str, Enum):
	EXPLICIT = "explicit"
	DERIVED = "derived"
	INFERRED = "inferred"


class TaskPriority(str, Enum):
	LOW = "LOW"
	MEDIUM = "MEDIUM"
	HIGH = "HIGH"


# Pattern-first extraction heuristics (LLD-aligned).
WINDOW_SCAN_SIZE = 3
WINDOW_SCAN_STEP = 1

API_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")
API_METHOD_ENDPOINT_REGEX = r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/[A-Za-z0-9_\-/{}/]+)"
API_ENDPOINT_FALLBACK_REGEX = r"/(?:api|v\d+)/[A-Za-z0-9_\-/{}/]+"

# Shared parsing regex patterns across sprint generation pipeline modules.
DOCX_NUMBERED_TEXT_REGEX = r"^\d+[\.)]\s+"
DOCX_HEADING_STYLE_REGEX = r"heading\s*(\d+)"

NORMALIZATION_API_TITLE_METHOD_ENDPOINT_REGEX = r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/\S+)$"
NORMALIZATION_API_DESC_SIGNATURE_REGEX = r"Signature:\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/\S+)"
NORMALIZATION_ENDPOINT_SUFFIX_REGEX = r"(/\S+)$"

RECONCILIATION_API_TITLE_WITH_METHOD_REGEX = r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+/[A-Za-z0-9_\-/{}/]+$"
RECONCILIATION_API_TITLE_ENDPOINT_ONLY_REGEX = r"^/[A-Za-z0-9_\-/{}/]+$"
RECONCILIATION_API_METHOD_ENDPOINT_PARSE_REGEX = r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/\S+)$"
RECONCILIATION_API_ENDPOINT_EXTRACT_REGEX = r"(/[A-Za-z0-9_\-/{}/]+)"
RECONCILIATION_SLASH_COLLAPSE_REGEX = r"/{2,}"
RECONCILIATION_PLACEHOLDER_TRIM_REGEX = r"^[{:<*]+|[}>]+$"
RECONCILIATION_SEGMENT_SANITIZE_REGEX = r"[^a-z0-9_]+"
RECONCILIATION_MULTI_UNDERSCORE_REGEX = r"_+"
RECONCILIATION_VERSION_SEGMENT_REGEX = r"/v\d+"
RECONCILIATION_WHITESPACE_REGEX = r"\s+"
RECONCILIATION_PLACEHOLDER_BLOCK_REGEX = r"\{[^}]+\}"
RECONCILIATION_ID_TOKEN_REGEX = r"\b(id|uuid|guid)\b"
RECONCILIATION_WORD_TOKEN_REGEX = r"\w+"
RECONCILIATION_NON_WORD_REGEX = r"[^\w]+"

TASK_GENERATION_API_TASK_NAME_REGEX = r"^(Implement|Verify)\s+(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|UPDATE)\s+(/\S+?)(\s+behavior)?$"
TASK_GENERATION_VERIFY_PREFIX_REGEX = r"^(verify|test|testing)\s+"
TASK_GENERATION_BEHAVIOR_SUFFIX_REGEX = r"\s+behavior$"
TASK_GENERATION_TEXT_SANITIZE_REGEX = r"[^\w/{}\s-]+"
TASK_GENERATION_WHITESPACE_REGEX = r"\s+"
TASK_GENERATION_TOKEN_REGEX = r"[\w/{}-]+"
TASK_GENERATION_ENDPOINT_SLASH_COLLAPSE_REGEX = r"/{2,}"
TASK_GENERATION_METHOD_REWRITE_REGEX = r"\b(PUT|PATCH)\b"
TASK_GENERATION_JSON_FENCE_REGEX = r"```(?:json)?\s*(.*?)\s*```"

# API structural normalization rules (shared across normalization/reconciliation).
# Only strip transport/version prefixes; do not strip domain prefixes like /admin or /internal.
API_NORMALIZATION_PREFIX_PATTERNS = (
	r"^/api(?:/v\d+)?/ts(?=/)",
	r"^/api(?:/v\d+)?(?=/)",
	r"^/v\d+(?=/)",
)

# Normalize different parameter syntaxes to a canonical placeholder segment.
API_NORMALIZATION_PARAM_PATTERNS = (
	r"^\{[^/]+\}$",  # {id}
	r"^:[^/]+$",       # :id
	r"^<[^/]+>$",      # <id>
	r"^\*$",           # *
)

# Explicit alias allowlist only; never apply fuzzy plural/singular mapping.
API_SEGMENT_ALIAS_ALLOWLIST = {
}

# Optional API contract gate. This is document-agnostic and validates signature shape.
# Signatures are normalized to: "METHOD /path/with/{}/params".
API_CONTRACT_GATE_ENABLED = True

# Base validity checks that should work for almost all API design documents.
API_CONTRACT_METHODS = API_METHODS
API_CONTRACT_MIN_SEGMENTS = 1
API_CONTRACT_ALLOW_ROOT = False
API_CONTRACT_SIGNATURE_REGEX = r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+/[a-z0-9_\-{}\/]+$"

# Optional project-specific strict allowlist. Keep empty for generic behavior.
API_CONTRACT_ALLOWED_SIGNATURE_REGEX: tuple[str, ...] = ()

# API method inference hints for EN/VI wording when endpoint exists but method is absent.
API_VERB_METHOD_HINTS: dict[str, str] = {
	# Create-like
	"create": "POST",
	"add": "POST",
	"new": "POST",
	"register": "POST",
	"signup": "POST",
	"submit": "POST",
	"import": "POST",
	"upload": "POST",
	"tao": "POST",
	"tạo": "POST",
	"them": "POST",
	"thêm": "POST",
	"dang ky": "POST",
	"đăng ký": "POST",
	"gui": "POST",
	"gửi": "POST",
	# Read-like
	"get": "GET",
	"list": "GET",
	"fetch": "GET",
	"read": "GET",
	"view": "GET",
	"detail": "GET",
	"search": "GET",
	"xem": "GET",
	"lay": "GET",
	"lấy": "GET",
	"danh sach": "GET",
	"danh sách": "GET",
	"tra cuu": "GET",
	"tra cứu": "GET",
	"tim": "GET",
	"tìm": "GET",
	# Update-like
	"update": "PUT",
	"edit": "PUT",
	"modify": "PUT",
	"change": "PATCH",
	"patch": "PATCH",
	"cap nhat": "PUT",
	"cập nhật": "PUT",
	"chinh sua": "PUT",
	"chỉnh sửa": "PUT",
	"sua": "PUT",
	"sửa": "PUT",
	"doi": "PATCH",
	"đổi": "PATCH",
	# Delete-like
	"delete": "DELETE",
	"remove": "DELETE",
	"destroy": "DELETE",
	"xoa": "DELETE",
	"xóa": "DELETE",
	"go": "DELETE",
	"gỡ": "DELETE",
}

TASK_VERBS_EN = (
	"implement",
	"build",
	"create",
	"add",
	"design",
	"update",
	"delete",
	"integrate",
	"setup",
	"configure",
	"develop",
	"refactor",
	"optimize",
	"migrate",
	"deploy",
	"document",
	"test",
	"verify",
	"fix",
	"improve",
	"analyze",
	"review",
	"monitor",
	"validate",
	"support",
	"maintain",
	"prepare",
	"define",
	"specify",
	"plan",
	"estimate",
	"breakdown",
	"groom",
	"sync",
	"align",
	"release",
	"harden",
	"secure",
	"profile",
	"benchmark",
)
TASK_VERBS_VI = (
	"xay dung",
	"xây dựng",
	"tao",
	"tạo",
	"thiet ke",
	"thiết kế",
	"trien khai",
	"triển khai",
	"cap nhat",
	"cập nhật",
	"xoa",
	"xóa",
	"tich hop",
	"tích hợp",
	"cau hinh",
	"cấu hình",
	"phat trien",
	"phát triển",
	"toi uu",
	"tối ưu",
	"tai cau truc",
	"tái cấu trúc",
	"chuan bi",
	"chuẩn bị",
	"lap ke hoach",
	"lập kế hoạch",
	"uoc luong",
	"ước lượng",
	"kiem thu",
	"kiểm thử",
	"xac minh",
	"xác minh",
	"phan tich",
	"phân tích",
	"danh gia",
	"đánh giá",
	"giam sat",
	"giám sát",
	"bao tri",
	"bảo trì",
	"ho tro",
	"hỗ trợ",
	"ghi tai lieu",
	"ghi tài liệu",
	"dong bo",
	"đồng bộ",
	"canh chinh",
	"căn chỉnh",
	"phat hanh",
	"phát hành",
	"bao mat",
	"bảo mật",
)

TASK_EXTRA_ACTION_PREFIXES = (
	"viet",
	"viết",
	"write",
	"author",
	"draft",
	"investigate",
	"research",
	"spike",
	"proof",
	"poc",
)

FEATURE_HEADING_KEYWORDS = (
	"feature",
	"module",
	"capability",
	"functional",
	"scope",
	"workflow",
	"flow",
	"sequence",
	"process",
	"journey",
	"component",
	"data model",
	"schema",
	"spec",
	"specification",
	"requirement",
	"requirements",
	"design",
	"architecture",
	"api",
	"endpoint",
	"ui",
	"screen",
	"page",
	"form",
	"chuc nang",
	"chức năng",
	"tinh nang",
	"tính năng",
	"kha nang",
	"khả năng",
	"dac ta",
	"đặc tả",
	"yeu cau",
	"yêu cầu",
	"thiet ke",
	"thiết kế",
	"luong",
	"luồng",
	"quy trinh",
	"quy trình",
	"trinh tu",
	"trình tự",
	"man hinh",
	"màn hình",
	"giao dien",
	"giao diện",
	"bieu mau",
	"biểu mẫu",
)

DB_CONSTRAINT_TOKENS = (
	"NOT NULL",
	"PRIMARY KEY",
	"FOREIGN KEY",
	"UNIQUE",
	"AUTO INCREMENT",
	"DEFAULT",
	"CHECK",
	"INDEX",
	"REFERENCES",
	"KHOA CHINH",
	"KHÓA CHÍNH",
	"KHOA NGOAI",
	"KHÓA NGOẠI",
	"KHONG RONG",
	"KHÔNG RỖNG",
	"DUY NHAT",
	"DUY NHẤT",
)


# Rule-based hard filter constants for final extraction gate.
EXTRACT_FILTER_JUNK_REGEX = r"^(.{0,2}|test|demo|example|asdf|qwerty|lorem|null|undefined)$"
EXTRACT_FILTER_MIN_TEXT_LENGTH = 6

# Semantic entropy guard for extraction signals.
EXTRACTION_SEMANTIC_ENTROPY_ENABLED = True
EXTRACTION_SEMANTIC_ENTROPY_THRESHOLD = 3.35
EXTRACTION_SEMANTIC_ENTROPY_MIN_TOKENS = 6
EXTRACTION_SEMANTIC_DOMAIN_MIN_HIT_RATIO = 0.08

# ============================================================
# 1. DOMAIN VOCABULARY (expanded for Business + SRS + Planning)
# ============================================================

EXTRACTION_DOMAIN_VOCABULARY = {
    # --- Core engineering ---
    "ai", "api", "db", "ui", "ux",
    "sql", "http", "https", "id",
    "jwt", "grpc", "rest",
    "ci", "cd", "ml",

    # --- System / architecture ---
    "srs",
    "sprint",
    "backlog",
	"ton dong",
	"tồn đọng",
    "sequence",
	"tuan tu",
	"tuần tự",
    "activity",
	"hoat dong",
	"hoạt động",
    "diagram",
	"so do",
	"sơ đồ",
    "workflow",
	"quy trinh",
	"quy trình",
    "service",
	"dich vu",
	"dịch vụ",
    "component",
	"thanh phan",
	"thành phần",
    "module",
	"phan he",
	"phân hệ",
    "system",
	"he thong",
	"hệ thống",
	"kien truc",
	"kiến trúc",

    # --- Business / product ---
    "user",
	"nguoi dung",
	"người dùng",
    "usecase",
    "use case",
	"truong hop su dung",
	"trường hợp sử dụng",
    "user story",
	"cau chuyen nguoi dung",
	"câu chuyện người dùng",
    "story",
	"cau chuyen",
	"câu chuyện",
    "epic",
	"epic lon",
    "feature",
	"tinh nang",
	"tính năng",
    "requirement",
	"yeu cau",
	"yêu cầu",
    "spec",
    "specification",
	"dac ta",
	"đặc tả",
    "business",
	"nghiep vu",
	"nghiệp vụ",
    "solution",
	"giai phap",
	"giải pháp",
    "scope",
	"pham vi",
	"phạm vi",

    # --- Planning / project management ---
    "task",
	"cong viec",
	"công việc",
    "subtask",
	"cong viec con",
	"công việc con",
    "plan",
	"ke hoach",
	"kế hoạch",
    "planning",
	"lap ke hoach",
	"lập kế hoạch",
    "roadmap",
	"lo trinh",
	"lộ trình",
    "milestone",
	"cot moc",
	"cột mốc",
    "timeline",
	"dong thoi gian",
	"dòng thời gian",
    "phase",
	"giai doan",
	"giai đoạn",
    "iteration",
	"vong lap",
	"vòng lặp",
    "sprint planning",
	"lap ke hoach sprint",
	"lập kế hoạch sprint",
    "backlog item",
	"hang muc backlog",
	"hạng mục backlog",

    # --- Data / design artifacts ---
    "schema",
	"luoc do",
	"lược đồ",
    "migration",
	"di chuyen du lieu",
	"di chuyển dữ liệu",
    "entity",
	"thuc the",
	"thực thể",
    "table",
	"bang",
	"bảng",
    "index",
	"chi muc",
	"chỉ mục",
    "api design",
	"thiet ke api",
	"thiết kế api",
    "data model",
	"mo hinh du lieu",
	"mô hình dữ liệu",
    "database",
	"co so du lieu",
	"cơ sở dữ liệu",
}

EXTRACTION_NOISE_TOKENS = {
    # --- generic placeholders ---
    "tmp", "test", "example", "sample",
    "dummy", "placeholder", "todo", "fixme",

    # --- common markdown / extraction artifacts ---
    "section", "chapter", "part", "figure", "table",
    "header", "footer",

    # --- weak semantic fillers ---
    "data",   # only keep if part of "data model", "data pipeline"
    "info",   # too generic
    "details",
    "description",  # often redundant noise

    # --- formatting artifacts ---
    "api/v1", "v1", "v2",
}

EXTRACTION_CANONICAL_PHRASE_MAP = {
    # --- DB / data ---
    "db schema": "Database Schema",
    "database schema": "Database Schema",
    "schema design": "Database Schema",
    "data schema": "Database Schema",
    "migration": "Database Migration",
    "db migration": "Database Migration",

    # --- API ---
    "api design": "API Design",
    "rest api": "API Design",
    "grpc api": "gRPC Design",
    "api endpoint": "API Endpoint",
    "endpoint design": "API Design",

    # --- SRS / requirements ---
    "srs": "Software Requirements Specification",
    "specification": "Specification",
    "requirement spec": "Software Requirements Specification",
    "user story": "User Story",
    "usecase": "Use Case",
    "use case": "Use Case",

    # --- diagrams ---
    "sequence diagram": "Sequence Diagram",
    "activity diagram": "Activity Diagram",
    "workflow diagram": "Workflow Diagram",

    # --- planning ---
    "planning": "Project Planning",
    "plan": "Project Plan",
    "roadmap": "Product Roadmap",
    "backlog": "Product Backlog",
    "sprint planning": "Sprint Planning",

    # --- UI / frontend ---
    "ui design": "UI Design",
    "ux design": "UX Design",
    "component design": "Component Design",

    # --- system design ---
    "system design": "System Design",
    "architecture design": "System Architecture Design",

    # --- feature abstraction ---
    "feature design": "Feature Design",
    "business logic": "Business Logic Design",
}

EXTRACT_FILTER_API_STRICT_REGEX = r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+/(?:[A-Za-z0-9_\-{}]+(?:/[A-Za-z0-9_\-{}]+)*)$"
EXTRACT_FILTER_API_FALLBACK_REGEX = r"^/(?:api|v\d+)/(?:[A-Za-z0-9_\-{}]+(?:/[A-Za-z0-9_\-{}]+)*)$"
EXTRACT_FILTER_BROKEN_ENDPOINT_REGEX = r"^/?[a-zA-Z0-9_\-]+(\s+[a-zA-Z0-9_\-]+)?$"

EXTRACT_FILTER_DB_COLUMN_REGEX = r"([a-zA-Z_]+)\s*:\s*([A-Za-z0-9()]+)"
EXTRACT_FILTER_DB_CONSTRAINT_REGEX = r"PRIMARY KEY|FOREIGN KEY|NOT NULL|UNIQUE"

EXTRACT_FILTER_FEATURE_NOISE_REGEX = r"^(overview|introduction|summary|general|misc|other|etc)\s*$"
EXTRACT_FILTER_TASK_WEAK_VERB_ONLY_REGEX = r"^(implement|create|build|update|delete|fix|add|design|setup)\s*$"
EXTRACT_FILTER_NOISE_BLACKLIST_REGEX = r"\b(test|testing|todo|fixme|hack|tmp|temporary|dummy|sample)\b"


# Task generation normalization constants.
VALID_TASK_PRIORITIES = {"LOW", "MEDIUM", "HIGH"}
VALID_TASK_STORY_POINTS = {1, 2, 3, 5, 8}
TASK_DUE_DATE_REGEX = r"^\d{4}-\d{2}-\d{2}$"
TASK_MIN_DYNAMIC_FLOOR = 12

# Critical-AI semantic dedup controls in task generation stage.
TASK_SEMANTIC_DEDUP_ENABLED = True
TASK_SEMANTIC_DEDUP_MAX_TRY = 3


# Normalization semantic filter thresholds.
NORMALIZATION_NEAREST_SIMILARITY_MIN = 0.35
NORMALIZATION_SINGLETON_SIMILARITY_MIN = 0.4


# Reconciliation merge constants.
RECONCILIATION_VALID_TYPES = {"feature", "task", "api", "db_schema"}

# Deterministic alias generation constants for reconciliation output.
RECONCILIATION_ALIAS_MAX_PER_ITEM = 6

RECONCILIATION_ALIAS_TASK_LEADING_VERBS = (
	"create",
	"update",
	"delete",
	"add",
	"remove",
	"implement",
	"fix",
	"build",
	"generate",
	"setup",
)

RECONCILIATION_ALIAS_NOISE_EXACT = {
	"out of scope",
	"in scope",
	"api detailed",
}

RECONCILIATION_DOMAIN_VOCABULARY = {
	"ai",
	"api",
	"db",
	"ui",
	"ux",
	"sql",
	"http",
	"https",
	"id",
	"jwt",
	"system",
	"architecture",
	"design",
	"module",
	"feature",
	"requirement",
	"scope",
	"diagram",
	"workflow",
	"sequence",
	"he thong",
	"hệ thống",
	"kien truc",
	"kiến trúc",
	"thiet ke",
	"thiết kế",
	"phan he",
	"phân hệ",
	"tinh nang",
	"tính năng",
	"yeu cau",
	"yêu cầu",
	"pham vi",
	"phạm vi",
	"so do",
	"sơ đồ",
	"quy trinh",
	"quy trình",
	"tuan tu",
	"tuần tự",
}

RECONCILIATION_TITLE_NOISE_TOKENS = {
	"for",
	"to",
	"the",
	"and",
	"or",
	"of",
	"in",
	"on",
	"at",
	"by",
	"with",
	"from",
}

# Hard-noise patterns for alias/title cleanup (normalized substring match).
RECONCILIATION_NOISE_PATTERNS = (
	# Scope / meta noise
	"in scope",
	"out of scope",
	"scope definition",
	"feature scope",
	"project scope",
	"scope overview",
	"scope",
	"trong pham vi",
	"ngoai pham vi",
	"pham vi",
	"dinh nghia pham vi",
	"pham vi tinh nang",
	"pham vi du an",
	"tong quan pham vi",
	# Design / architecture document noise
	"system design",
	"high level design",
	"low level design",
	"detailed design",
	"architecture design",
	"architecture overview",
	"technical design",
	"design document",
	"requirements analysis",
	"analysis document",
	"system overview",
	"technical overview",
	"thiet ke he thong",
	"thiet ke tong quan",
	"thiet ke chi tiet",
	"kien truc he thong",
	"tong quan kien truc",
	"thiet ke ky thuat",
	"tai lieu thiet ke",
	"dac ta",
	"phan tich yeu cau",
	"tai lieu phan tich",
	"tong quan he thong",
	"tong quan ky thuat",
	# UML / diagram noise
	"sequence diagram",
	"class diagram",
	"use case diagram",
	"flow diagram",
	"state diagram",
	"er diagram",
	"entity relationship diagram",
	"uml diagram",
	"activity diagram",
	"so do tuan tu",
	"so do lop",
	"so do use case",
	"so do luong",
	"so do trang thai",
	"so do er",
	"so do quan he thuc the",
	"so do uml",
	"so do hoat dong",
	# Generic engineering noise
	"feature overview",
	"module overview",
	"api detailed",
	"api specification",
	"service overview",
	"system module",
	"tong quan tinh nang",
	"tong quan module",
	"api chi tiet",
	"dac ta api",
	"tong quan service",
	"module he thong",
	# Abstract / non-atomic noise
	"improve system",
	"system improvement",
	"enhance system",
	"optimize system",
	"refactor system",
	"enhance performance",
	"improve performance",
	"technical improvement",
	"system enhancement",
	"cai thien he thong",
	"cai tien he thong",
	"nang cap he thong",
	"toi uu he thong",
	"tai cau truc he thong",
	"cai thien hieu nang",
	"cai thien hieu suat",
	"cai tien ky thuat",
	# LLM artifact noise
	"document analysis",
	"system analysis",
	"requirement analysis",
	"design analysis",
	"planning document",
	"implementation plan",
	"phan tich tai lieu",
	"phan tich he thong",
	"phan tich thiet ke",
	"tai lieu ke hoach",
	"ke hoach trien khai",
	# Generic / low-information noise
	"overview",
	"details",
	"detailed",
	"general system",
	"feature module",
	"specification",
	"spec",
	"tong quan",
	"chi tiet",
	"he thong tong quat",
	"module tinh nang",
)

# Scoring-based noise flags for shorter/generic aliases.
RECONCILIATION_NOISE_DOC_HINTS = (
	"design",
	"architecture",
	"diagram",
	"overview",
	"analysis",
	"spec",
	"specification",
	"document",
	"scope",
	"module",
	"api",
	"tong quan",
	"phan tich",
	"dac ta",
	"tai lieu",
	"pham vi",
	"so do",
	"thiet ke",
	"kien truc",
)

RECONCILIATION_NOISE_PREFIXES = (
	"system",
	"feature",
	"module",
	"he thong",
	"tinh nang",
)

RECONCILIATION_NOISE_SCORE_THRESHOLD = 2

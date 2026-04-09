from enum import Enum


class LLMModel(str, Enum):
	GEMINI_3_1_FLASH_LITE = "gemini-3.1-flash-lite-preview"
	GEMINI_3_0_FLASH = "gemini-3-flash-preview"
	GEMINI_2_5_FLASH = "gemini-2.5-flash"
	GEMINI_2_5_PRO = "gemini-2.5-pro"
	GEMINI_1_5_FLASH = "gemini-1.5-flash"
	GEMINI_1_5_PRO = "gemini-1.5-pro"


class LLMAgentName(str, Enum):
	EXTRACTION = "extraction"
	RECONCILIATION = "reconciliation"
	TASK_GENERATION = "task_generation"


class EmbedderModel(str, Enum):
	ALL_MINILM_L6_V2 = "all-MiniLM-L6-v2"


class StorageProvider(str, Enum):
	R2 = "r2"


R2_ENDPOINT_TEMPLATE = "https://{account_id}.r2.cloudflarestorage.com"

def BuildReconciliationPrompt() -> str:
    return build_final_prompt()


def build_role() -> str:
    return "You are a Type-Safe Semantic Merge Engine."


def build_objective() -> str:
	return "Merge multiple clusters (same-type within each cluster) into canonical items in one pass."


def build_input_schema() -> str:
    return """
"input_schema": {
	"clusters": [
		{
			"type": "feature | task | user_flow | api | db_schema",
			"cluster_id": "string",
			"items": [
				{
					"title": "string",
					"description": "string | null",
					"source": {
						"file_name": "string",
						"file_type": "Planning | Requirement | Design"
					}
				}
			]
		}
	]
}
""".strip()


def build_output_schema() -> str:
		return """
"output_schema": {
	"merged_items": [
		{
			"type": "feature | task | user_flow | api | db_schema",
			"title": "string",
			"description": "string",
			"aliases": ["string"],
			"source": [
				{
					"file_name": "string",
					"file_type": "Planning | Requirement | Design"
				}
			],
			"cluster_id": "string"
		}
	]
}
""".strip()


def build_type_rules() -> str:
		return """
"type_rules": {
	"feature": [
		"High-level capability",
		"No low-level technical detail"
	],
	"task": [
		"Must be actionable",
		"Prefer verb-based title (Implement, Create, Add...)"
	],
	"user_flow": [
		"Represents user journey",
		"Keep flow meaning"
	],
	"api": [
		"Technical endpoint",
		"Preserve method + endpoint meaning"
	],
	"db_schema": [
		"Data structure only",
		"No business logic"
	]
}
""".strip()


def build_rules() -> str:
		return """
"rules": [
	"Use only attached file_data JSON as input.",
	"Process every cluster in input.clusters.",
	"Return exactly one merged item per input cluster.",
	"Never drop or create extra clusters.",
	"Keep output type equal to the cluster input type.",
	"Never mix or convert types.",
	"Do not generalize beyond original scope.",
	"No hallucination, no new concepts.",
	"Choose canonical title by most complete, specific, and common wording.",
	"Description must be concise and complete; remove duplicates and contradictory details.",
	"Aliases must be semantically equivalent and deduplicated case-insensitively.",
	"Deduplicate source by (file_name, file_type) and sort file_name ascending.",
	"Keep cluster_id unchanged from input cluster.",
	"If no meaningful merge, use representative item and keep other titles as aliases.",
	"Output valid JSON only with top-level key merged_items.",
	"Do not include markdown, code fences, or explanation text."
]
""".strip()


def build_strategy() -> str:
		return """
"strategy": [
	"For each cluster, understand meaning and keep strict type boundary.",
	"Merge title and description.",
	"Collect aliases and deduplicated sources.",
	"Repeat for all clusters and return merged_items."
]
""".strip()


def build_final_prompt() -> str:
		return f"""
{{
	"role": "{build_role()}",
	"objective": "{build_objective()}",
	"input_mode": "attached_file_data_json",
	{build_input_schema()},
	{build_output_schema()},
	{build_type_rules()},
	{build_rules()},
	{build_strategy()}
}}
""".strip()

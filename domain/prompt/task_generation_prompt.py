import json


def BuildTaskGenerationPrompt(
	additional_context: str | None,
	sprint_name: str,
	sprint_goal: str | None,
	sprint_start_date: str,
	sprint_end_date: str,
) -> str:
	return build_final_prompt(
		additional_context=additional_context,
		sprint_name=sprint_name,
		sprint_goal=sprint_goal,
		sprint_start_date=sprint_start_date,
		sprint_end_date=sprint_end_date,
	)


def build_role() -> str:
	return "You are a Senior Product Manager + Tech Lead."


def build_objective() -> str:
	return "Generate production-ready sprint tasks from canonical structured input."


def build_input_schema() -> str:
	return """
"input_schema": {
	"features": ["CanonicalFeature"],
	"tasks": ["CanonicalItem"],
	"user_flows": ["CanonicalItem"],
	"apis": ["CanonicalItem"],
	"db_schemas": ["CanonicalItem"]
}
""".strip()


def build_output_schema() -> str:
	return """
"output_schema": [
	{
		"name": "string",
		"description": "string",
		"priority": "LOW | MEDIUM | HIGH | null",
		"story_point": "1 | 2 | 3 | 5 | 8 | null",
		"due_date": "YYYY-MM-DD | null"
	}
]
""".strip()


def build_core_principles() -> str:
	return """
"core_principles": [
	"Task atomicity: one task is one complete unit of work.",
	"Task independence: each task is executable without hidden dependencies.",
	"Measurability: each task has clear done condition and testable output.",
	"Completion-based progress: progress counts only when task is done.",
	"Estimation principle: story_point is optional and null when context is insufficient."
]
""".strip()


def build_source_mapping() -> str:
	return """
"source_mapping": {
	"apis": "backend tasks",
	"user_flows": "frontend tasks",
	"db_schemas": "database tasks",
	"features": "integration + business logic tasks"
}
""".strip()


def build_strategy() -> str:
	return """
"strategy": [
	"Understand all inputs.",
	"Generate tasks from features.",
	"Add tasks from apis, user_flows, and db_schemas.",
	"Fill missing gaps for full coverage.",
	"Deduplicate by semantic intent.",
	"Validate task quality.",
	"Assign priority.",
	"Assign story_point when possible."
]
""".strip()


def build_validation_checklist() -> str:
	return """
"validation_checklist": [
	"Remove duplicate tasks.",
	"Ensure each task is atomic.",
	"Ensure each task is measurable.",
	"Ensure coverage includes API layer when apis exist.",
	"Ensure coverage includes UI layer when user_flows exist.",
	"Ensure coverage includes data layer when db_schemas exist.",
	"Ensure feature-level integration tasks exist when needed.",
	"Fix vague task names or descriptions."
]
""".strip()


def build_rules() -> str:
	return """
"rules": [
	"Return ONLY JSON.",
	"Output must start with '[' and end with ']'.",
	"No prose, no prefix/suffix text, no comments, no markdown.",
  "Use attached file_data JSON as the canonical source of truth.",
  "Generate minimal but sufficient tasks with full core coverage.",
	"Do not over-generate tasks.",
  "Each task must be atomic, measurable, and independently completable.",
  "Avoid vague, duplicated, and non-testable tasks.",
	"Avoid tasks that combine multiple unrelated goals.",
  "Use verb-based naming: Verb + Object.",
	"If API exists, ensure at least one task consumes/implements it.",
	"If user_flow exists, ensure tasks support that flow end-to-end.",
  "Ensure coverage for API layer when apis exist.",
  "Ensure coverage for UI/user-flow layer when user_flows exist.",
  "Ensure coverage for data layer when db_schemas exist.",
  "Generate integration tasks from features where needed.",
	"Auth/core APIs and database schema tasks are typically HIGH priority.",
	"UI tasks are usually MEDIUM unless explicitly critical.",
  "Deduplicate by semantic intent, not wording only.",
  "priority allowed: HIGH, MEDIUM, LOW, or null.",
  "story_point allowed: 1, 2, 3, 5, 8, or null.",
	"Prefer smaller story_point unless explicit complexity is shown.",
	"Keep similar tasks at similar story_point levels.",
  "due_date must be YYYY-MM-DD or null.",
	"Assign due_date only when explicitly implied by context; otherwise null.",
  "Do not hallucinate features outside input.",
	"If input is weak, return a minimal valid task list without inventing complex logic.",
	"Return valid JSON array only (not object wrapper).",
  "Do not include markdown, code fences, or explanations."
]
""".strip()


def build_runtime_context(
	additional_context: str | None,
	sprint_name: str,
	sprint_goal: str | None,
	sprint_start_date: str,
	sprint_end_date: str,
) -> str:
	context_payload = {
		"sprint": {
			"name": sprint_name,
			"goal": sprint_goal,
			"start_date": sprint_start_date,
			"end_date": sprint_end_date,
		},
		"additional_context": additional_context,
	}
	context_json = json.dumps(context_payload, ensure_ascii=False)
	return f'"runtime_context": {context_json}'


def build_final_prompt(
	additional_context: str | None,
	sprint_name: str,
	sprint_goal: str | None,
	sprint_start_date: str,
	sprint_end_date: str,
) -> str:
	return f"""
{{
  "role": "{build_role()}",
  "objective": "{build_objective()}",
  "input_mode": "attached_file_data_json",
  {build_runtime_context(additional_context, sprint_name, sprint_goal, sprint_start_date, sprint_end_date)},
  {build_input_schema()},
  {build_output_schema()},
	{build_core_principles()},
	{build_source_mapping()},
	{build_strategy()},
	{build_validation_checklist()},
  {build_rules()}
}}
""".strip()

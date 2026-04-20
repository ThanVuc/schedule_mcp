import json


def BuildTaskGenerationPrompt(
    additional_context: str | None,
    sprint_name: str,
    sprint_goal: str | None,
    sprint_start_date: str,
    sprint_end_date: str,
    target_min_tasks: int | None = None,
) -> str:
    return build_final_prompt(
        additional_context,
        sprint_name,
        sprint_goal,
        sprint_start_date,
        sprint_end_date,
        target_min_tasks,
    )


def BuildTaskExpansionPrompt(
    sprint_name: str,
    sprint_goal: str | None,
    sprint_start_date: str,
    sprint_end_date: str,
    target_min_tasks: int,
    existing_tasks: list[dict],
) -> str:
    return build_expansion_prompt(
        sprint_name,
        sprint_goal,
        sprint_start_date,
        sprint_end_date,
        target_min_tasks,
        existing_tasks,
    )


def build_role():
    return "You are a Senior Product Manager + Tech Lead."


def build_objective():
    return "Generate atomic, production-ready sprint tasks from structured input."


def build_prompt_body():
    return """
{
  "input_schema": {
    "features": [],
    "tasks": [],
    "user_flows": [],
    "apis": [],
    "db_schemas": []
  },

  "output_schema": [
    {
      "name": "string",
      "description": "string",
      "source_file_name": "string",
      "source_file_type": "Planning | Design | Requirement",
      "signal_origin": "explicit | derived | inferred",
      "priority": "LOW | MEDIUM | HIGH | null",
      "story_point": "1 | 2 | 3 | 5 | 8 | null",
      "due_date": "YYYY-MM-DD | null"
    }
  ],

  "rule_priority": [
    "rules",
    "qa_generation_rules",
    "frontend_generation_rules",
    "layer_coverage_rules",
    "minimum_coverage_rules"
  ],

  "rules": [
    "Return ONLY JSON array.",
    "Each task = 1 PR, 0.5–2 days.",
    "Task name: Verb + Layer + Specific Component.",
    "No vague verbs (handle/manage/process).",
    "Do NOT combine UI, API, DB in one task.",
    "Do not hallucinate outside input.",
    "Set null if unsure.",
    "Respect additional_context."
  ],

  "story_point_rules": [
    "1 point = 0.5 day",
    "Use 1–4 points per task",
    "Split tasks instead of exceeding"
  ],

  "layer_coverage_rules": [
    "APIs -> backend tasks",
    "DB -> schema + migration",
    "Frontend -> from user_flows or features"
  ],

  "frontend_generation_rules": [
    "Derive from features if no user_flows",
    "Group small actions (create/update/export) into ONE task",
    "Do NOT split UI per API",
    "Each task = complete UI unit"
  ],

  "qa_generation_rules": [
    "Generate QA tasks if explicit QA intent exists",
    "If only features exist, allow feature-level QA tasks",
    "Do NOT derive QA from APIs",
    "Do NOT create QA per endpoint"
  ],

  "minimum_coverage_rules": [
    "Per feature: >=2-3 tasks if enough context",
    "Per API: >=1 backend task",
    "Per DB: >=2 tasks",
    "Do not leave layers uncovered"
  ],

  "strategy": [
    "Understand inputs",
    "Generate design if missing",
    "Then backend → frontend → integration",
    "Deduplicate by intent",
    "Ensure coverage before finishing"
  ]
}
""".strip()


def build_runtime_context(
    additional_context,
    sprint_name,
    sprint_goal,
    sprint_start_date,
    sprint_end_date,
    target_min_tasks,
):
    payload = {
        "sprint": {
            "name": sprint_name,
            "goal": sprint_goal,
            "start_date": sprint_start_date,
            "end_date": sprint_end_date,
        },
        "additional_context": additional_context,
        "target_min_tasks": target_min_tasks,
    }
    return json.dumps(payload, ensure_ascii=False)


def build_final_prompt(
    additional_context,
    sprint_name,
    sprint_goal,
    sprint_start_date,
    sprint_end_date,
    target_min_tasks,
):
    return f"""
{{
  "role": "{build_role()}",
  "objective": "{build_objective()}",
  "input_mode": "attached_file_data_json",
  "runtime_context": {build_runtime_context(
      additional_context,
      sprint_name,
      sprint_goal,
      sprint_start_date,
      sprint_end_date,
      target_min_tasks
  )},
  {build_prompt_body()}
}}
""".strip()


def build_expansion_prompt(
    sprint_name,
    sprint_goal,
    sprint_start_date,
    sprint_end_date,
    target_min_tasks,
    existing_tasks,
):
    payload = {
        "sprint": {
            "name": sprint_name,
            "goal": sprint_goal,
            "start_date": sprint_start_date,
            "end_date": sprint_end_date,
        },
        "target_min_tasks": target_min_tasks,
        "existing_tasks": existing_tasks,
    }

    return f"""
{{
  "role": "{build_role()}",
  "objective": "Expand tasks without duplication.",
  "input_mode": "attached_file_data_json",
  "runtime_context": {json.dumps(payload, ensure_ascii=False)},
  "rules": [
    "Return ONLY JSON array.",
    "Generate ONLY new tasks.",
    "Do not duplicate by intent.",
    "Follow same coverage + frontend + QA rules as base.",
    "Ensure total >= target_min_tasks."
  ]
}}
""".strip()

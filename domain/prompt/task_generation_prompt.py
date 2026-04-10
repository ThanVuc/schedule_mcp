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
    return "Generate atomic, production-ready sprint tasks from canonical structured input."


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
    "Task atomicity: one task equals one pull request.",
    "Task independence: no hidden dependencies.",
    "Measurability: each task must be testable.",
    "Granularity: each task should take 0.5–2 days.",
    "Avoid high-level or vague tasks.",
    "Prefer multiple small tasks over few large tasks."
]
""".strip()


def build_task_decomposition_rules() -> str:
    return """
"task_decomposition_rules": [
    "Decompose each feature into layers: Design → Backend → Frontend → Integration → Testing.",
    "Each layer must be split into separate atomic tasks.",
    "Do not combine multiple layers into a single task.",
    "Prefer 5–15 small tasks per feature instead of large tasks."
]
""".strip()


def build_design_rules() -> str:
    return """
"design_rules": [
    "If database schema is missing or unclear, generate a DB design task.",
    "If API contract is missing, generate API request/response design task.",
    "If system flow is complex, generate sequence/flow design task.",
    "Design tasks must come before implementation tasks."
]
""".strip()


def build_layer_coverage_rules() -> str:
    return """
"layer_coverage_rules": [
    "If APIs exist → generate backend implementation and API test tasks.",
    "If user_flows exist → generate frontend UI tasks.",
    "If both frontend and backend exist → generate integration tasks.",
    "If db_schemas exist → generate schema + migration tasks.",
    "Infra/system tasks may skip UI but must include setup and validation tasks."
]
""".strip()


def build_examples() -> str:
    return """
"examples": {
    "bad_tasks": [
        "Develop Document Parsing Pipeline",
        "Implement AI Sprint Generation API",
        "Build Authentication System"
    ],
    "good_tasks": [
        "Implement file upload endpoint for document ingestion",
        "Parse markdown into structured sections",
        "Extract API definitions from document content",
        "Create API endpoint to trigger sprint generation",
        "Add RBAC middleware for sprint API",
        "Build UI form to upload sprint document",
        "Write unit tests for parsing logic",
        "Connect UI to sprint generation API"
    ]
}
""".strip()


def build_strategy() -> str:
    return """
"strategy": [
    "Understand all inputs.",
    "For each feature, identify required layers: design, backend, frontend, integration, testing.",
    "Generate design tasks first if missing.",
    "Generate backend (API/logic) tasks.",
    "Generate frontend tasks only if user_flows exist.",
    "Generate integration tasks connecting components.",
    "Generate testing tasks to validate behavior.",
    "Ensure each task is atomic and independently executable.",
    "Deduplicate by semantic intent.",
    "Validate full layer coverage.",
    "Assign priority and story_point."
]
""".strip()


def build_validation_checklist() -> str:
    return """
"validation_checklist": [
    "Remove duplicate tasks.",
    "Ensure each task is atomic (1 PR).",
    "Ensure each task is testable.",
    "Ensure no task describes a full system or pipeline.",
    "Ensure backend, frontend, and data layers are covered when applicable.",
    "Ensure tasks are not vague or high-level.",
    "Fix generic wording like 'system', 'pipeline', 'logic'."
]
""".strip()


def build_rules() -> str:
    return """
"rules": [
    "Return ONLY JSON.",
    "Output must start with '[' and end with ']'.",
    "No prose, no markdown, no explanations.",
    "Use attached file_data JSON as the source of truth.",
    
    "Each task must be atomic and correspond to a single PR.",
    "Each task must be completable within 0.5–2 days.",
    
    "Do NOT generate high-level tasks like 'build system' or 'develop pipeline'.",
    "Do NOT combine UI, API, and DB work into one task.",
    
    "Task name must be Verb + Specific Component.",
    "Avoid generic nouns like 'system', 'pipeline', 'logic', 'feature'.",
    
    "If APIs exist, ensure implementation and test tasks.",
    "If user_flows exist, ensure UI tasks.",
    "If db_schemas exist, ensure DB tasks.",
    
    "priority allowed: HIGH, MEDIUM, LOW, or null.",
    "story_point allowed: 1, 2, 3, 5, 8, or null.",
    "due_date must be YYYY-MM-DD or null.",
    
    "Do not hallucinate features outside input.",
    "If input is weak, return minimal valid tasks.",
    "Return valid JSON array only."
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
  {build_task_decomposition_rules()},
  {build_design_rules()},
  {build_layer_coverage_rules()},
  {build_examples()},
  {build_strategy()},
  {build_validation_checklist()},
  {build_rules()}
}}
""".strip()

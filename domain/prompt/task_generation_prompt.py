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
        additional_context=additional_context,
        sprint_name=sprint_name,
        sprint_goal=sprint_goal,
        sprint_start_date=sprint_start_date,
        sprint_end_date=sprint_end_date,
        target_min_tasks=target_min_tasks,
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
        sprint_name=sprint_name,
        sprint_goal=sprint_goal,
        sprint_start_date=sprint_start_date,
        sprint_end_date=sprint_end_date,
        target_min_tasks=target_min_tasks,
        existing_tasks=existing_tasks,
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
        "source_file_name": "string",
        "source_file_type": "Planning | Design | Requirement",
        "signal_origin": "explicit | derived | inferred",
        "priority": "LOW | MEDIUM | HIGH | null",
        "story_point": "1 | 2 | 3 | 5 | 8 | null",
        "due_date": "YYYY-MM-DD | null"
    }
]
""".strip()


def build_core_principles() -> str:
    return """
"core_principles": [
    "One task = one PR.",
    "Each task must be independently testable and completable in 0.5-2 days.",
    "Prefer small concrete tasks over vague high-level tasks.",
    "Prioritize complete layer coverage over brevity."
]
""".strip()


def build_minimum_coverage_rules() -> str:
    return """
"minimum_coverage_rules": [
    "Per feature: >=3 tasks when context is sufficient.",
    "Per API: >=2 tasks (implementation + testing).",
    "Per user_flow: >=2 tasks (UI + integration/E2E).",
    "Per db_schema: >=2 tasks (schema/migration + data access).",
    "Do not stop while uncovered layers remain."
]
""".strip()


def build_task_decomposition_rules() -> str:
    return """
"task_decomposition_rules": [
    "Decompose by layer: Design -> Backend -> Frontend -> Integration -> Testing.",
    "Split each layer into atomic tasks.",
    "Do not combine multiple layers in one task.",
    "Prefer many small tasks (roughly 5-15 per feature) over large tasks."
]
""".strip()


def build_design_rules() -> str:
    return """
"design_rules": [
    "If DB schema is missing/unclear, generate a DB design task.",
    "If API contract is missing, generate request/response contract design task.",
    "If flow is complex, generate sequence/flow design task.",
    "Design tasks must come before implementation tasks."
]
""".strip()

def build_api_specific_rules() -> str:
    return """
"api_task_rules": [
    "Generate at least one implementation task per API.",
    "For CRUD APIs, split tasks per action when possible.",
    "Generate API tasks even without feature mapping."
]
""".strip()


def build_layer_coverage_rules() -> str:
    return """
"layer_coverage_rules": [
    "APIs -> backend implementation + API tests.",
    "user_flows -> frontend UI tasks.",
    "frontend + backend -> integration tasks.",
    "db_schemas -> schema + migration tasks.",
    "Infra/system work may skip UI but must include setup + validation tasks."
]
""".strip()


def build_strategy() -> str:
    return """
"strategy": [
    "Understand all inputs.",
    "Identify required layers per feature (design/backend/frontend/integration/testing).",
    "Generate missing design tasks first, then implementation and validation tasks.",
    "Generate frontend tasks only when user_flows exist.",
    "Deduplicate by intent and validate full coverage.",
    "Assign priority and story_point."
]
""".strip()


def build_validation_checklist() -> str:
    return """
"validation_checklist": [
    "Remove duplicate tasks.",
    "Keep tasks atomic, testable, and non-vague.",
    "Reject full-system/pipeline tasks.",
    "Ensure backend/frontend/data layers are covered when applicable.",
    "Fix generic wording like system/pipeline/logic."
]
""".strip()


def build_primary_signal_rules() -> str:
    return """
"primary_signal_rules": [
    "Primary signal order: planning tasks -> design APIs/DB -> feature fallback.",
    "If Planning tasks exist, preserve planning explicit intent tasks and never delete them.",
    "If no planning tasks but design signals exist, APIs and DB schemas are primary coverage targets.",
    "If only feature signals exist, generate technical design tasks from features."
]
""".strip()


def build_coverage_and_critic_rules() -> str:
    return """
"coverage_and_critic_rules": [
    "Each primary item must map to at least one generated task.",
    "In design mode: per API generate implementation + QC/verification tasks.",
    "In design mode: per DB schema generate schema + migration tasks.",
    "Use deterministic source propagation: preserve source_file_name/source_file_type/signal_origin from origin item.",
    "Regenerate only missing/invalid subset when coverage fails.",
    "Keep unaffected tasks unchanged during regeneration.",
    "Never return an empty task list when canonical signals are present."
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
    "source_file_name is required and must come from contributing source lineage.",
    "source_file_type allowed: Planning, Design, Requirement.",
    "signal_origin allowed: explicit, derived, inferred.",

    "Do not hallucinate features outside input.",
    "If input is weak, still generate concrete layer-coverage tasks from available APIs, user flows, and db schemas.",
    "If runtime_context.target_min_tasks exists, generate at least that many tasks unless input is empty.",
    "When planning explicit tasks exist, keep them as user-intent and do not remove or rewrite intent.",
    "Return valid JSON array only."
]
""".strip()

def build_fall_back_rules() -> str:
    return """
"fallback_rules": [
  "If APIs exist but no features, derive tasks directly from APIs.",
  "If DB schemas exist, generate schema and migration tasks.",
  "Never return empty tasks when APIs are present."
]
""".strip()

def build_runtime_context(
    additional_context: str | None,
    sprint_name: str,
    sprint_goal: str | None,
    sprint_start_date: str,
    sprint_end_date: str,
    target_min_tasks: int | None = None,
) -> str:
    context_payload = {
        "sprint": {
            "name": sprint_name,
            "goal": sprint_goal,
            "start_date": sprint_start_date,
            "end_date": sprint_end_date,
        },
        "additional_context": additional_context,
        "target_min_tasks": target_min_tasks,
    }
    context_json = json.dumps(context_payload, ensure_ascii=False)
    return f'"runtime_context": {context_json}'


def build_final_prompt(
    additional_context: str | None,
    sprint_name: str,
    sprint_goal: str | None,
    sprint_start_date: str,
    sprint_end_date: str,
    target_min_tasks: int | None = None,
) -> str:
    return f"""
{{
  "role": "{build_role()}",
  "objective": "{build_objective()}",
  "input_mode": "attached_file_data_json",
    {build_runtime_context(additional_context, sprint_name, sprint_goal, sprint_start_date, sprint_end_date, target_min_tasks)},
  {build_input_schema()},
  {build_output_schema()},
  {build_core_principles()},
    {build_minimum_coverage_rules()},
  {build_task_decomposition_rules()},
  {build_design_rules()},
  {build_api_specific_rules()},
  {build_layer_coverage_rules()},
  {build_strategy()},
  {build_validation_checklist()},
    {build_primary_signal_rules()},
    {build_coverage_and_critic_rules()},
  {build_rules()},
  {build_fall_back_rules()},
  CRITICAL: PLEASE RESPECT THE ADDITIONAL_CONTEXT
}}
""".strip()


def build_expansion_prompt(
        sprint_name: str,
        sprint_goal: str | None,
        sprint_start_date: str,
        sprint_end_date: str,
        target_min_tasks: int,
        existing_tasks: list[dict],
) -> str:
        context_payload = {
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
    "objective": "Expand existing tasks to reach minimum coverage and count without duplicates.",
    "input_mode": "attached_file_data_json",
    "runtime_context": {json.dumps(context_payload, ensure_ascii=False)},
    "output_schema": [
        {{
            "name": "string",
            "description": "string",
            "source_file_name": "string",
            "source_file_type": "Planning | Design | Requirement",
            "signal_origin": "explicit | derived | inferred",
            "priority": "LOW | MEDIUM | HIGH | null",
            "story_point": "1 | 2 | 3 | 5 | 8 | null",
            "due_date": "YYYY-MM-DD | null"
        }}
    ],
    "rules": [
        "Return ONLY JSON array.",
        "Generate ONLY NEW tasks not overlapping existing_tasks by intent.",
        "Prefer missing layer tasks (design, backend, frontend, integration, testing).",
        "Respect minimum_coverage_rules from base prompt.",
        "Generate enough new tasks so existing + new >= target_min_tasks when feasible.",
        "Do not return explanations or markdown."
    ]
}}
""".strip()

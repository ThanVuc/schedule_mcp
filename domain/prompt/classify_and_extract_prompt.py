def BuildClassifyAndExtractPrompt() -> str:
    return build_final_prompt()


def build_role() -> str:
    return "You are a Senior Business + Technical Analyst."


def build_objective() -> str:
    return (
        "Extract structured JSON from ONE attached file. "
        "No cross-file inference. No semantic merge."
    )


def build_input_schema() -> str:
    return """
"input_schema": {
  "uri": "string (from attached file_data.file_uri)",
  "mime": "string (from attached file_data.mime_type)"
}
""".strip()


def build_output_schema() -> str:
    return """
"output_schema": {
  "file_name": "string",
  "type": "Planning | Requirement | Design",
  "features": [
    { "title": "string", "description": "string | null" }
  ],
  "tasks": [
    {
      "title": "string",
      "description": "string | null",
      "related_feature": "string | null"
    }
  ],
  "user_flows": [
    { "name": "string", "steps": ["string"] }
  ],
  "apis": [
    {
      "name": "string",
      "endpoint": "string | null",
      "method": "GET|POST|PUT|DELETE|PATCH | null",
      "description": "string | null"
    }
  ],
  "db_schema": [
    {
      "table": "string",
      "columns": [
        {
          "name": "string",
          "type": "string | null",
          "constraints": ["string"]
        }
      ]
    }
  ]
}
""".strip()


def build_rules() -> str:
  return """
"rules": [
  "Process one file only (1 file = 1 AI call).",
  "Use attached file_data as the only source of file content.",
  "Input schema only uses uri and mime from attached file_data metadata.",
  "Set file_name exactly equal to uri.",
  "Determine type with this priority: filename prefix first, content fallback second.",
  "Extract base filename from uri (lowercase, ignore extension) before checking prefix.",
  "If filename starts with prefix 'design' (design_, design-, design ) => type must be Design.",
  "If filename starts with prefix 'planning' (planning_, planning-, planning ) => type must be Planning.",
  "If filename starts with prefix 'requirement' (requirement_, requirement-, requirement ) => type must be Requirement.",
  "Only when no valid prefix exists, infer type from file content.",
  "Fallback content rule: Design if technical specs dominate (API contracts, DB schema, sequence/state/component diagrams, integration contracts, data models).",
  "Fallback content rule: Requirement if requirement artifacts dominate (user stories, acceptance criteria, business rules, personas, user journeys).",
  "Fallback content rule: Planning if planning artifacts dominate (scope, goals, milestones, timeline, roadmap, effort plan).",
  "If fallback evidence is mixed, choose the most technical type in this order: Design > Requirement > Planning.",
  "Extract only what is explicitly present in the file.",
  "No cross-file linking.",
  "No semantic merge.",
  "No guessing missing data.",
  "Always return all collections: features, tasks, user_flows, apis, db_schema.",
  "Use [] for missing collections.",
  "Never return null for collections.",
  "Keep output JSON only, no markdown, no explanation.",
  "Do not wrap output in code fences."
]
""".strip()


def build_priority_hints() -> str:
    return """
"type_priority_hints": {
  "Design": ["apis", "db_schema"],
  "Requirement": ["features", "user_flows"],
  "Planning": ["tasks", "features"]
}
""".strip()


def build_final_prompt() -> str:
    return f"""
{{
  "role": "{build_role()}",
  "objective": "{build_objective()}",
  {build_input_schema()},
  {build_output_schema()},
  {build_priority_hints()},
  {build_rules()}
}}
""".strip()

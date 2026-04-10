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


def build_priority_hints() -> str:
    return """
"type_priority_hints": {
  "Design": ["apis", "db_schema"],
  "Requirement": ["features", "user_flows"],
  "Planning": ["tasks", "features"]
}
""".strip()


def build_extraction_strategy() -> str:
    return """
"extraction_strategy": [
  "Scan the entire document before extracting.",
  "Identify logical sections such as Features, APIs, Database, User Flows, Tasks.",
  "Extract structured data section by section.",
  "Prefer structured formats (tables, lists, code blocks) over free text.",
  "If sections are not explicit, infer based on patterns."
]
""".strip()


def build_pattern_rules() -> str:
    return """
"pattern_rules": [
  "APIs: detect HTTP methods (GET, POST, PUT, DELETE, PATCH) and endpoints (/path).",
  "APIs: extract name from nearby heading or description.",
  
  "DB schema: detect tables, columns, and types from tables or structured lists.",
  "DB schema: extract constraints only if explicitly stated (PRIMARY KEY, FOREIGN KEY, NOT NULL, UNIQUE).",
  
  "User flows: detect ordered steps, numbered lists, or sequential actions.",
  
  "Features: detect headings or high-level capability descriptions.",
  
  "Tasks: detect action-oriented items using verbs (implement, build, create, design, add, integrate)."
]
""".strip()


def build_normalization_rules() -> str:
    return """
"normalization_rules": [
  "Trim whitespace and normalize casing.",
  "Keep naming concise but specific.",
  "Avoid duplicate entries within the same section.",
  "Merge identical items within the same file.",
  "Use consistent naming for APIs and tables."
]
""".strip()


def build_hallucination_rules() -> str:
    return """
"hallucination_rules": [
  "Only extract data explicitly present in the file.",
  "If a field is unclear or missing, set it to null.",
  "Do not infer endpoints, schema, or fields.",
  "Do not create synthetic features, APIs, or tasks."
]
""".strip()


def build_user_flow_rules() -> str:
    return """
"user_flow_rules": [
  "Each user flow must have a clear name.",
  "Steps must be sequential and action-based.",
  "Do not merge multiple flows into one.",
  "Ignore non-actionable descriptions."
]
""".strip()


def build_api_rules() -> str:
    return """
"api_rules": [
  "Each API must include method if explicitly present.",
  "Each API must include endpoint if explicitly present.",
  "If method or endpoint is missing, set to null.",
  "Do not guess missing API details."
]
""".strip()


def build_rules() -> str:
    return """
"rules": [
  "Process one file only (1 file = 1 AI call).",
  "Use attached file_data as the only source.",
  "Set file_name exactly equal to uri.",
  
  "Determine type using filename prefix first, then content fallback.",
  "Extract base filename (lowercase, ignore extension) before checking prefix.",
  
  "Prefix rules:",
  "design_* => Design",
  "planning_* => Planning",
  "requirement_* => Requirement",
  
  "Fallback type rules:",
  "Design if technical content dominates.",
  "Requirement if business/user logic dominates.",
  "Planning if timeline/scope dominates.",
  
  "If mixed, choose priority: Design > Requirement > Planning.",
  
  "Always return all collections.",
  "Use [] for missing collections.",
  "Never return null for collections.",
  "Return exactly one JSON object matching output_schema.",
  "All string values must be valid JSON strings (escape internal quotes and backslashes).",
  "Do not include raw newlines inside string values; use escaped \\n when needed.",
  
  "Output JSON only.",
  "No markdown, no explanation, no code fences."
]
""".strip()


def build_final_prompt() -> str:
    return f"""
{{
  "role": "{build_role()}",
  "objective": "{build_objective()}",
  {build_input_schema()},
  {build_output_schema()},
  {build_priority_hints()},
  {build_extraction_strategy()},
  {build_pattern_rules()},
  {build_normalization_rules()},
  {build_hallucination_rules()},
  {build_user_flow_rules()},
  {build_api_rules()},
  {build_rules()}
}}
""".strip()
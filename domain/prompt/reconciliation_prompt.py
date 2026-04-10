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


def build_merge_validation_rules() -> str:
    return """
"merge_validation_rules": [
    "All items in a cluster must represent the same semantic intent.",
    "If items represent different actions or conflicting meanings, do NOT merge into a generalized concept.",
    "If conflict exists, select the most representative item.",
    "Do NOT merge opposite actions (e.g., create vs delete)."
]
""".strip()


def build_granularity_rules() -> str:
    return """
"granularity_rules": [
    "Do NOT generalize into high-level concepts like 'system', 'pipeline', or 'management'.",
    "Keep the same level of detail as input items.",
    "Prefer concrete and actionable titles.",
    "If input items are atomic, output must remain atomic."
]
""".strip()


def build_examples() -> str:
    return """
"examples": {
    "bad_merges": [
        {
            "input": ["Create user API", "Delete user API"],
            "wrong_output": "User API management",
            "reason": "Different actions must not be merged"
        }
    ],
    "good_merges": [
        {
            "input": ["Create user API", "Implement user creation endpoint"],
            "output": "Implement user creation API",
            "reason": "Same semantic intent"
        }
    ]
}
""".strip()


def build_rules() -> str:
    return """
"rules": [
    "Use only attached file_data JSON as input.",
    "Process every cluster in input.clusters.",
    "Return exactly one merged item per cluster.",
    "Never drop or create extra clusters.",
    "Keep output type equal to input type.",
    "Never mix or convert types.",
    
    "Choose canonical title that is specific, actionable, and representative.",
    "Avoid vague or abstract titles.",
    "Preserve action verbs and technical specificity.",
    
    "Description must be concise and complete.",
    "Remove duplicate or conflicting information.",
    
    "Aliases must be semantically equivalent only.",
    "Do not include broader or conflicting terms as aliases.",
    "Deduplicate aliases case-insensitively.",
    
    "Deduplicate source by (file_name, file_type).",
    "Sort source by file_name ascending.",
    
    "Keep cluster_id unchanged.",
    
    "If no meaningful merge, select one representative item.",
    
    "No hallucination, no new concepts.",
    
    "Output valid JSON only with top-level key merged_items.",
    "Do not include markdown, code fences, or explanation text."
]
""".strip()


def build_strategy() -> str:
    return """
"strategy": [
    "For each cluster, analyze all items and confirm shared semantic intent.",
    "Detect conflicts in action, scope, or meaning.",
    "If consistent, merge into a single canonical representation.",
    "If inconsistent, select the most representative item without generalizing.",
    "Construct a precise and specific title.",
    "Merge descriptions while removing duplication.",
    "Collect aliases only if semantically equivalent.",
    "Aggregate and deduplicate sources.",
    "Repeat for all clusters."
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
    {build_merge_validation_rules()},
    {build_granularity_rules()},
    {build_examples()},
    {build_rules()},
    {build_strategy()}
}}
""".strip()

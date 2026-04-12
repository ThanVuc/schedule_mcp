def build_merge_role() -> str:
    return "You are a Deterministic Semantic Cluster Merger."


def build_merge_objective() -> str:
    return (
        "Merge clusters into a single canonical representative per cluster "
        "without enrichment, without aliases, and without abstraction."
    )


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


def build_merge_output_schema() -> str:
    return """
"output_schema": {
    "merged_items": [
        {
            "type": "feature | task | user_flow | api | db_schema",
            "title": "string",
            "description": "string",
            "cluster_id": "string",
            "source": [
                {
                    "file_name": "string",
                    "file_type": "Planning | Requirement | Design"
                }
            ]
        }
    ]
}
""".strip()


def build_merge_rules() -> str:
    return """
"rules": [
    "Process each cluster independently.",
    "Return exactly one merged item per cluster.",
    "DO NOT generate aliases.",
    "DO NOT enrich or expand meaning.",
    "DO NOT generalize or abstract concepts.",
    "DO NOT infer new entities or schemas.",
    "DO NOT merge conflicting actions or intents.",
    "Keep strict type safety.",
    "Keep original granularity.",
    "If uncertain, select the most representative item.",
    "No hallucination.",
    "Output valid JSON only."
]
""".strip()


def build_merge_strategy() -> str:
    return """
"strategy": [
    "Analyze cluster items for semantic consistency.",
    "Detect conflicts in action or meaning.",
    "If consistent, merge into canonical representation.",
    "If inconsistent, select most representative item.",
    "Preserve original intent strictly.",
    "Do not modify meaning."
]
""".strip()


def build_merge_prompt() -> str:
    return f"""
{{
    "role": "{build_merge_role()}",
    "objective": "{build_merge_objective()}",
    "input_mode": "attached_file_data_json",
    {build_input_schema()},
    {build_merge_output_schema()},
    {build_merge_rules()},
    {build_merge_strategy()}
}}
""".strip()

def BuildReconciliationMergePrompt() -> str:
    return build_merge_prompt()
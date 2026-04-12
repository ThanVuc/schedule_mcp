from typing import List


def build_translate_prompt(texts: List[str], target_language: str = "English") -> str:
    """
    Build a deterministic translation prompt for pivot-language normalization.

    Purpose:
    - Translate multilingual documentation into English
    - Preserve technical tokens (API, DB, placeholders, code, etc.)
    - Output structured JSON for pipeline consumption
    """

    def format_inputs(items: List[str]) -> str:
        return "\n".join([f"[{i}] {t}" for i, t in enumerate(items)])

    return f"""
You are a high-precision translation engine for a software information extraction system.

========================
TASK
========================
Translate ALL input text into {target_language}.

========================
HARD RULES (MUST FOLLOW)
========================
1. Do NOT change meaning.
2. Do NOT summarize or expand.
3. Do NOT interpret or infer missing information.
4. Output must be strictly faithful to the input.
5. Preserve markdown structure exactly (headings, bullets, numbering, code fences, tables, blockquotes).
6. Keep line breaks and table delimiters '|' intact whenever possible.
7. Do not rewrite formatting layout; only translate natural-language text.

========================
PRESERVE EXACTLY (DO NOT TRANSLATE)
========================
- API paths (e.g. /api/v1/users)
- Database fields and schema names
- Code identifiers (camelCase, snake_case)
- Placeholders like {{id}}, {{user_id}}, {{}}
- UUIDs, hashes, timestamps
- HTTP methods (GET, POST, PATCH, DELETE)
- Technical acronyms (API, DB, SQL, UI, UX, JWT, gRPC)
- File names and system identifiers

========================
DOMAIN CONTEXT
========================
This text is from software/system documentation:
- system design
- API specification
- database schema
- feature descriptions
- task definitions

Use **technical English**, not conversational English.

========================
NORMALIZATION RULES
========================
- Prefer canonical engineering terms:
  - "db schema" → "database schema"
  - "api" → "API"
  - "migration" → "database migration"
- Keep output concise and structured
- Do not add explanations

========================
OUTPUT FORMAT (STRICT)
========================
Return ONLY valid JSON:

{{
  "translations": [
    {{
      "original": "...",
      "translated": "..."
    }}
  ]
}}

========================
INPUT TEXTS
========================
{format_inputs(texts)}
""".strip()

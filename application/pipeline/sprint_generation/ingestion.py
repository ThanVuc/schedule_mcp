import asyncio
import io
import logging
import os
import re

import pandas as pd
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from application.dtos.common import FileDTO
from infrastructure.base.llm.gemini_llm import LLMConnector
from infrastructure.base.storage.storage import Storage


EXTRACTION_CONTEXT_HINT = (
    "This content is extracted from files. Structure may be imperfect. "
    "Interpret intelligently."
)


def _is_blank_cell(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() == ""


def _normalize_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _slugify_header(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned if cleaned else fallback


def split_blocks(sheet_df: pd.DataFrame) -> list[pd.DataFrame]:
    blocks: list[pd.DataFrame] = []
    current_rows: list[list[object]] = []

    for _, row in sheet_df.iterrows():
        row_values = row.tolist()
        if all(_is_blank_cell(cell) for cell in row_values):
            if current_rows:
                blocks.append(pd.DataFrame(current_rows))
                current_rows = []
            continue
        current_rows.append(row_values)

    if current_rows:
        blocks.append(pd.DataFrame(current_rows))

    return blocks


def clean_dataframe(block_df: pd.DataFrame) -> pd.DataFrame:
    if block_df.empty:
        return pd.DataFrame()

    working = block_df.copy()

    # Resolve common merged-cell artifacts for downstream parsing.
    working = working.ffill(axis=0)

    # Remove empty rows/columns.
    working = working.dropna(axis=0, how="all")
    working = working.dropna(axis=1, how="all")
    if working.empty:
        return pd.DataFrame()

    working = working.reset_index(drop=True)

    header_row = working.iloc[0].tolist()
    data_rows = working.iloc[1:].reset_index(drop=True)

    headers: list[str] = []
    seen_headers: dict[str, int] = {}
    for idx, raw_header in enumerate(header_row):
        candidate = _slugify_header(_normalize_text(raw_header), f"column_{idx + 1}")
        if candidate in seen_headers:
            seen_headers[candidate] += 1
            candidate = f"{candidate}_{seen_headers[candidate]}"
        else:
            seen_headers[candidate] = 1
        headers.append(candidate)

    data_rows.columns = headers

    # Drop columns that are still empty after header extraction.
    non_empty_cols = [
        col for col in data_rows.columns
        if data_rows[col].map(lambda v: _normalize_text(v) != "").any()
    ]
    cleaned = data_rows[non_empty_cols] if non_empty_cols else pd.DataFrame(columns=headers)

    return cleaned


def _to_markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "(empty table)"

    headers = list(df.columns)
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"

    body_lines: list[str] = []
    for _, row in df.iterrows():
        cells = [_normalize_text(row[col]) for col in headers]
        body_lines.append("| " + " | ".join(cells) + " |")

    return "\n".join([header_line, separator_line, *body_lines])


def _iter_docx_blocks(document: DocxDocument):
    """Yield Paragraph and Table objects in the original document order."""
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def _docx_table_to_markdown(table: Table) -> str:
    rows: list[list[str]] = []

    for row in table.rows:
        cells = [_normalize_text(cell.text) for cell in row.cells]
        if any(cell != "" for cell in cells):
            rows.append(cells)

    if not rows:
        return ""

    max_cols = max(len(row) for row in rows)
    normalized_rows: list[list[str]] = [
        row + [""] * (max_cols - len(row))
        for row in rows
    ]

    raw_headers = normalized_rows[0]
    headers: list[str] = []
    seen: dict[str, int] = {}
    for idx, header in enumerate(raw_headers):
        candidate = _slugify_header(header, f"column_{idx + 1}")
        if candidate in seen:
            seen[candidate] += 1
            candidate = f"{candidate}_{seen[candidate]}"
        else:
            seen[candidate] = 1
        headers.append(_escape_md_cell(candidate))

    body_rows = normalized_rows[1:]

    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"

    if not body_rows:
        return "\n".join([header_line, separator_line])

    body_lines = []
    for row in body_rows:
        body_lines.append(
            "| " + " | ".join(_escape_md_cell(_normalize_text(cell)) for cell in row) + " |"
        )

    return "\n".join([header_line, separator_line, *body_lines])


def _paragraph_has_numbering(paragraph: Paragraph) -> bool:
    p_pr = paragraph._p.pPr
    if p_pr is None:
        return False
    return p_pr.numPr is not None


def _normalize_list_text(text: str) -> str:
    # Remove common leading list glyphs to avoid duplicating bullets in markdown.
    return re.sub(r"^[\u2022\u25CF\u25E6\-\*\s]+", "", text).strip()


def _is_numbered_text(text: str) -> bool:
    return bool(re.match(r"^\d+[\.|\)]\s+", text))


def parse_docx(content: bytes) -> str:
    output_lines: list[str] = []

    try:
        document = Document(io.BytesIO(content))
    except Exception as exc:
        logging.exception("docx parse failed")
        return f"# Parse Error\n\nUnable to parse DOCX content: {exc}"

    table_idx = 0
    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue

            style_name = (block.style.name or "").lower() if block.style else ""

            heading_match = re.search(r"heading\s*(\d+)", style_name)
            if heading_match:
                level = max(1, min(6, int(heading_match.group(1))))
                output_lines.append(f"{'#' * level} {text}")
                continue

            has_numbering = _paragraph_has_numbering(block)
            normalized_text = _normalize_list_text(text)

            # Handle list paragraphs based on Word numbering metadata and style names.
            if has_numbering or "list" in style_name:
                if "list number" in style_name or _is_numbered_text(text):
                    output_lines.append(f"1. {normalized_text}")
                else:
                    output_lines.append(f"- {normalized_text}")
                continue

            output_lines.append(text)
            continue

        if isinstance(block, Table):
            table_md = _docx_table_to_markdown(block)
            if not table_md:
                continue

            table_idx += 1
            output_lines.append(f"## Table {table_idx}")
            output_lines.append(table_md)

    return "\n\n".join(output_lines).strip()


def parse_excel(content: bytes) -> str:
    sections: list[str] = []

    try:
        workbook = pd.read_excel(
            io.BytesIO(content),
            sheet_name=None,
            header=None,
            engine="openpyxl",
        )
    except Exception as exc:
        logging.exception("excel parse failed")
        return f"# Parse Error\n\nUnable to parse XLSX content: {exc}"

    if not workbook:
        return "# Excel\n\n(empty workbook)"

    for sheet_name, sheet_df in workbook.items():
        sections.append(f"## Sheet: {sheet_name}")

        blocks = split_blocks(sheet_df)
        if not blocks:
            sections.append("(empty sheet)")
            continue

        for idx, block_df in enumerate(blocks, start=1):
            cleaned_df = clean_dataframe(block_df)
            sections.append(f"### Table {idx}")
            sections.append(_to_markdown_table(cleaned_df))

    return "\n\n".join(section for section in sections if section).strip()


def _render_extracted_markdown(object_key: str, content: bytes, mime: str) -> tuple[bytes, str, str]:
    extension = os.path.splitext(object_key)[1].lower()
    file_name = os.path.basename(object_key)

    markdown_body: str | None = None
    if extension == ".docx" or "word" in mime:
        markdown_body = parse_docx(content)
    elif extension == ".xlsx" or "spreadsheet" in mime or "excel" in mime:
        markdown_body = parse_excel(content)

    if markdown_body is None:
        return content, mime, object_key

    wrapped_markdown = (
        f"# Source File\n\n{file_name}\n\n"
        f"{EXTRACTION_CONTEXT_HINT}\n\n"
        f"{markdown_body}\n"
    )

    markdown_key = re.sub(r"\.[^.]+$", ".md", object_key)
    return wrapped_markdown.encode("utf-8"), "text/markdown", markdown_key


class IngestionPipeline:
    def __init__(self, storage: Storage, llm: LLMConnector, max_concurrency: int = 5):
        self.storage = storage
        self.llm = llm
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def ingest(self, object_keys: list[str]) -> list[FileDTO]:
        tasks = [
            self._process_object(object_key)
            for object_key in object_keys
        ]

        ingested_objects = await asyncio.gather(*tasks)

        return ingested_objects

    # 👇 each file = 1 async task
    async def _process_object(self, object_key: str) -> FileDTO:
        async with self._semaphore:
            # 1. Download file from R2
            content, mime = await self.storage.download_with_robust_mime(object_key)

            if mime is None:
                mime = "application/octet-stream"  # default fallback

            # 2. Preprocess unsupported office files to markdown for LLM extraction.
            upload_content, upload_mime, upload_key = _render_extracted_markdown(
                object_key=object_key,
                content=content,
                mime=mime,
            )

            # print a markdown file for testing (evidence)
            os.makedirs("z_evidence/ingestion", exist_ok=True)
            with open(f"z_evidence/ingestion/{os.path.basename(upload_key)}", "wb") as f:
                f.write(upload_content)

            # 3. Upload file to LLM and get a reference (e.g. file_id or URL)
            return await self.llm.upload_file(
                object_key=upload_key,
                content=upload_content,
                mime=upload_mime,
            )

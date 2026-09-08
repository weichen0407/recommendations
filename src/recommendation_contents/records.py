"""Persist topic workflow results as table files."""

from __future__ import annotations

import csv
import json
from pathlib import Path

RECORD_HEADERS = [
    "input",
    "generated_prompt",
    "session_url",
    "share_url",
    "title",
    "categories",
    "keywords",
    "description",
    "role",
    "industry",
    "jtbd",
    "date",
    "sub_industry",
]
LEGACY_HEADER_MAP = {
    "输入": "input",
    "generate prompt 后的 prompt": "generated_prompt",
    "session 会话链接": "session_url",
    "最终分享链接": "share_url",
}
DEFAULT_RECORDS_CSV = "outputs/topic_workflow_records.csv"
DEFAULT_RECORDS_MARKDOWN = "outputs/topic_workflow_records.md"


def save_result_table(
    row: dict[str, str],
    csv_path: str = DEFAULT_RECORDS_CSV,
    markdown_path: str = DEFAULT_RECORDS_MARKDOWN,
) -> None:
    append_csv_row(row=row, csv_path=csv_path)
    rows = read_csv_rows(csv_path)
    write_markdown_table(rows=rows, markdown_path=markdown_path)


def append_csv_row(row: dict[str, str], csv_path: str) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _migrate_csv_schema(path)
    file_exists = path.exists() and path.stat().st_size > 0

    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RECORD_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({header: row.get(header, "") for header in RECORD_HEADERS})


def read_csv_rows(csv_path: str) -> list[dict[str, str]]:
    path = Path(csv_path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as file:
        return [
            {header: row.get(header, "") for header in RECORD_HEADERS}
            for row in csv.DictReader(file)
        ]


def _migrate_csv_schema(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        if fieldnames == RECORD_HEADERS:
            return
        rows = [_normalize_legacy_row(row) for row in reader]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RECORD_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _normalize_legacy_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {header: row.get(header, "") for header in RECORD_HEADERS}
    for legacy_header, current_header in LEGACY_HEADER_MAP.items():
        if not normalized[current_header] and row.get(legacy_header):
            normalized[current_header] = row[legacy_header]
    return normalized


def write_markdown_table(rows: list[dict[str, str]], markdown_path: str) -> None:
    path = Path(markdown_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_table(rows), encoding="utf-8")


def build_markdown_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "| " + " | ".join(RECORD_HEADERS) + " |",
        "| " + " | ".join(["---"] * len(RECORD_HEADERS)) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(_markdown_cell(row.get(header, "")) for header in RECORD_HEADERS)
            + " |"
        )
    return "\n".join(lines) + "\n"


def _markdown_cell(value: str) -> str:
    text = _display_value(value)
    return text.replace("|", "\\|").replace("\n", "<br>").strip()


def _display_value(value: str) -> str:
    if not isinstance(value, str):
        return str(value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, list):
        return ", ".join(str(item) for item in parsed)
    return value

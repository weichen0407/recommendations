"""Convert generated records CSV files into PLG default-case JSON."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

PLG_OUTPUT_FILENAME = "plg-rd-case-default-us.json"
LIST_FIELDS = {"categories", "keywords", "jtbd", "sub_industry"}
PLG_FIELDS = [
    "input",
    "generated_prompt",
    "session_id",
    "share_id",
    "format",
    "isCompleted",
    "completionStatus",
    "completionError",
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a generated records CSV into plg-rd-case-default-us.json.",
    )
    parser.add_argument("records_csv", help="Path to the records CSV.")
    parser.add_argument(
        "--output-json",
        default="",
        help=(
            "Destination JSON path. Defaults to plg-rd-case-default-us.json in the same folder "
            "as the records CSV."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["html", "report"],
        default="",
        help="Content format to write. Defaults to inferring from the path.",
    )
    parser.add_argument(
        "--update-records-format",
        action="store_true",
        help="Also add/fill the format column in the source CSV.",
    )
    parser.add_argument("--pretty", action="store_true", default=True, help=argparse.SUPPRESS)
    args = parser.parse_args()

    records_path = Path(args.records_csv)
    generation_format = args.format or infer_format_from_path(records_path)
    if not generation_format:
        raise SystemExit("Could not infer format from path; pass --format html or --format report.")

    output_path = Path(args.output_json) if args.output_json else default_plg_output_path(records_path)
    rows = read_records_csv(records_path)
    items = [plg_item_from_row(row, generation_format) for row in rows]
    write_plg_json(items, output_path)

    if args.update_records_format:
        update_records_csv_format(records_path, generation_format)

    print(f"records={len(items)} format={generation_format} output_json={output_path}")


def read_records_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def plg_item_from_row(row: dict[str, Any], generation_format: str = "") -> dict[str, Any]:
    row_format = _string(row.get("format")) or _string(row.get("generation_mode")) or generation_format
    item: dict[str, Any] = {}
    for field in PLG_FIELDS:
        if field == "session_id":
            item[field] = _session_id_from_row(row)
        elif field == "share_id":
            item[field] = _share_id_from_row(row)
        elif field == "format":
            item[field] = row_format
        elif field in LIST_FIELDS:
            item[field] = _list_value(row.get(field))
        else:
            item[field] = _string(row.get(field))
    return item


def write_plg_json(items: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_records_csv_format(path: Path, generation_format: str) -> int:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = _with_format_field(list(reader.fieldnames or []))
        rows = list(reader)

    updated = 0
    for row in rows:
        if not _string(row.get("format")):
            row["format"] = generation_format
            updated += 1

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fieldnames} for row in rows])
    return updated


def default_plg_output_path(records_path: Path) -> Path:
    return records_path.parent / PLG_OUTPUT_FILENAME


def infer_format_from_path(path: Path) -> str:
    parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    if "html" in parts or "_html_" in name or name.endswith("_html_records.csv"):
        return "html"
    if "report" in parts or "_report_" in name or name.endswith("_report_records.csv"):
        return "report"
    return ""


def _with_format_field(fieldnames: list[str]) -> list[str]:
    if not fieldnames:
        return ["format"]
    fields = [field for field in fieldnames if field != "format"]
    try:
        index = fields.index("share_url") + 1
    except ValueError:
        index = min(4, len(fields))
    fields.insert(index, "format")
    return fields


def _session_id_from_row(row: dict[str, Any]) -> str:
    explicit = _string(row.get("session_id"))
    if explicit:
        return explicit
    match = re.search(r"sess_[A-Za-z0-9_-]+", _string(row.get("session_url")))
    return match.group(0) if match else ""


def _share_id_from_row(row: dict[str, Any]) -> str:
    explicit = _string(row.get("share_id"))
    if explicit:
        return explicit

    value = _string(row.get("share_url"))
    if not value:
        return ""

    parsed = urlparse(value)
    query_id = parse_qs(parsed.query).get("id")
    if query_id and query_id[0]:
        return query_id[0]

    match = re.search(r"[?&]id=([^&]+)", value)
    return unquote(match.group(1)) if match else ""


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_string(item) for item in value if _string(item)]
    if not isinstance(value, str):
        return []

    text = value.strip()
    if not text:
        return []

    parsed: Any = text
    for _ in range(2):
        if not isinstance(parsed, str):
            break
        candidate = parsed.strip()
        if not candidate.startswith("["):
            break
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            break

    if isinstance(parsed, list):
        return [_string(item) for item in parsed if _string(item)]
    if isinstance(parsed, str):
        return [parsed.strip()] if parsed.strip() else []
    return []


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


if __name__ == "__main__":
    main()

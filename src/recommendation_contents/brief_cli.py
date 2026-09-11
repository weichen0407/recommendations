"""Generate stage-one briefs or inspect their schema without starting Eureka tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .brief_schema import (
    LANGUAGES,
    MAX_BRIEFS,
    SCHEMA_VERSION,
    build_brief_schema,
    load_brief_catalog,
    parse_brief_response,
    validate_briefs,
)
from .config import apply_env_file_to_process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Operations idea to content description, target audience, and tags"
    )
    parser.add_argument("idea", nargs="?", help="Topic, trend, entity name, or short idea")
    parser.add_argument("--language", choices=LANGUAGES, default="zh-CN")
    parser.add_argument("--count", type=int, choices=range(1, MAX_BRIEFS + 1), default=1)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output-file", type=Path, help="Save JSON to a file; default: stdout")
    inspect = parser.add_mutually_exclusive_group()
    inspect.add_argument("--schema", action="store_true", help="Export response schema without LLM")
    inspect.add_argument(
        "--profile-schema",
        action="store_true",
        help="Export the fixed-profile Node 1 seven-facet schema without LLM",
    )
    inspect.add_argument(
        "--validate-file", type=Path, help="Validate a model response or saved topics offline"
    )
    args = parser.parse_args(argv)
    if args.idea is not None and (args.schema or args.profile_schema or args.validate_file):
        parser.error("idea cannot be combined with schema export or --validate-file")
    exit_code = 0
    if args.schema:
        data = build_brief_schema()
    elif args.profile_schema:
        from .profile_topic_generation import build_profile_topic_schema

        data = build_profile_topic_schema()
    elif args.validate_file:
        try:
            payload = parse_brief_response(args.validate_file.read_text(encoding="utf-8"))
            # Saved results contain code-assigned IDs; model responses must not supply them.
            if isinstance(payload, dict) and "generation_id" in payload:
                if payload.get("status") != "succeeded":
                    raise ValueError("saved generation did not succeed")
                if payload.get("schema_version") != SCHEMA_VERSION:
                    raise ValueError("unsupported schema version")
                if payload.get("taxonomy_version") != load_brief_catalog()["taxonomy_version"]:
                    raise ValueError("unsupported taxonomy version")
                count = payload["input"]["count"]
                payload = {
                    "briefs": [
                        {k: v for k, v in brief.items() if k != "brief_id"}
                        for brief in payload["briefs"]
                    ]
                }
            else:
                count = None
            errors = validate_briefs(payload, count=count)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            errors = [f"Cannot validate input file ({type(exc).__name__})."]
        data = {"valid": not errors, "errors": errors}
        exit_code = 1 if errors else 0
    else:
        if args.idea is None:
            parser.error(
                "idea is required unless --schema, --profile-schema or --validate-file is used"
            )
        from .brief_graph import build_brief_graph

        apply_env_file_to_process(args.env_file)
        data = build_brief_graph(env_file=args.env_file).invoke(
            {
                "idea": args.idea,
                "language": args.language,
                "count": args.count,
            },
            config={"run_name": "content_brief_workflow"},
        )["result"]
        exit_code = 0 if data["status"] == "succeeded" else 1
    output = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.output_file:
        args.output_file.parent.mkdir(parents=True, exist_ok=True)
        args.output_file.write_text(output, encoding="utf-8")
        print(f"Saved JSON: {args.output_file}")
    else:
        print(output, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

# Recommend Content 091010 Folder Standard

This folder is for the September 10, 10:00 content recommendation batch.
The current workflow assumes `subject.json` already exists. Later, an agent step can generate
`subject.csv` and `subject.json` from `enum_entities.json`, then reuse the same run commands.

Minimal structure:

```text
outputs/
  recommend-content-counts.csv
  0910/
    091010/
      subject.csv
      subject.json
      subject_distribution_preview.csv
      plg-rd-case-default-us.json
      report/
        *_records.csv
      html/
        *_records.csv
```

Rules:

- `subject.csv` stores draft subjects used to build curl prompts. Draft subjects do not update the count table until approved and generated.
- `subject_distribution_preview.csv` summarizes this draft distribution for review.
- `report/` stores report records when this batch has report generation.
- `html/` stores HTML records when this batch has HTML generation.
- `plg-rd-case-default-us.json` is the product-facing JSON derived from completed records.
- `outputs/recommend-content-counts.csv` is the global counter by industry, sub-industry, and content category.
- `usage.csv` and `results.json` are optional debugging/cost files. Keep them only when needed.
- URL fields should be normalized before writing product JSON:
  - `session_url` -> `session_id`, keeping only the `sess_...` value.
  - `share_url` -> `share_id`, keeping only the value between `id=` and `&from`.
- List-like fields must be real JSON arrays, not escaped strings. For example, use `["trend_brief"]`, not `"[\"trend_brief\"]"`.

Run examples:

```bash
uv run case-workflow outputs/0910/091010/subject.json --mode report --limit 144
uv run case-workflow outputs/0910/091010/subject.json --mode html --limit 144
```

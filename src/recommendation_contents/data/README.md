# Recommendation Tag Rule Artifacts

This directory contains the two machine-readable rule artifacts used by Node 1.

## `content_brief_catalog.json`

This is the maintained source of truth for taxonomy semantics and compatibility rules. It defines:

- audience enums for role, industry, and JTBD;
- the allowed second-level and facet enums;
- parent-child and cross-facet compatibility mappings;
- default-selection and classification policies.

The prompt builder reads a focused subset of this catalog, and runtime validation checks generated
content against its mappings.

## `profile_topic.schema.json`

This is the generated JSON Schema for the Node 1 model response. It defines required fields, data
types, enum values, array limits, and the seven-tag output shape. It is useful for structured-output
configuration, offline response validation, contract review, and integration tests. Its
`x-taxonomy-version` and `x-catalog-file` fields identify the catalog revision used to generate it.

JSON Schema describes the response shape. The catalog describes semantic relationships that JSON
Schema does not express cleanly, such as which JTBD tasks or topic themes are compatible. Keeping
the two artifacts separate avoids duplicating those relationships while placing both files in one
directory makes their ownership and versioning clear.

Regenerate the schema after changing the catalog:

```bash
uv run content-brief-workflow --profile-schema \
  --output-file src/recommendation_contents/data/profile_topic.schema.json
```

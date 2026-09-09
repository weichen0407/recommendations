"""Prompt builders for recommendation content generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .dates import today_iso
from .schemas import article_metadata_extraction_schema, prompt_generation_output_schema

SYSTEM_INSTRUCTIONS = """You are a senior prompt engineer for Eureka research/report generation.
Expand the user's short topic into a structured report record and a complete, task-ready prompt
for Eureka. Do not answer the topic itself."""

ARTICLE_EXTRACTION_SYSTEM_INSTRUCTIONS = """You are a precise content taxonomist.
Extract structured metadata from an existing article. Do not rewrite the article, summarize it
as a report, or add facts that are not supported by the article."""


def build_prompt_generation_prompt(state: Mapping[str, Any]) -> str:
    context = state.get("request_context") or {}
    output_schema = prompt_generation_output_schema()

    return f"""{SYSTEM_INSTRUCTIONS}

Topic:
{state.get("topic", "")}

Context JSON:
{json.dumps(context, ensure_ascii=False, indent=2)}

Output JSON schema:
{json.dumps(output_schema, ensure_ascii=False, indent=2)}

Return valid JSON only. Do not wrap it in Markdown fences.

Field requirements:
- title: create a clear, searchable title for the generated report.
- categories: choose the best content type(s) from the categories enum. Prefer one primary
  category unless the topic clearly needs more.
- keywords: include concrete technical, product, market, or problem keywords; avoid broad filler.
- description: summarize what the report will cover and why it is useful.
- role: choose the best target user role from the role enum.
- industry: choose the best industry from the industry enum.
- jtbd: choose one or more jobs-to-be-done from the jtbd enum.
- date: use today's date: {today_iso()}.
- sub_industry: choose relevant values from the sub_industry enum.
- prompt: write a complete report-generation prompt in Chinese unless context explicitly asks for
  another language. Keep it concise and complete: target 800-1400 Chinese characters, and do not
  stop mid-sentence.

The prompt field must be directly executable by Eureka and should include these parts without
over-expanding any single section:

1. Role
Ask Eureka to act as a senior research analyst. Choose the analyst type from the topic and
context, such as industry analyst, patent analyst, competitive intelligence analyst, market
analyst, technology strategy analyst, or investment research analyst.

2. Objective
Turn the topic into a clear report objective. Specify what decision, insight, comparison,
opportunity, risk, or strategy the report should support.

3. Scope and assumptions
Define the analysis scope, geography, time horizon, target audience, and any constraints from
Context JSON. If context is missing, ask Eureka to state reasonable assumptions before analysis.

4. Research steps
Ask Eureka to gather and synthesize evidence, then analyze the topic from the most relevant
dimensions. Prefer concrete dimensions such as market size and growth, technology evolution,
patent landscape, product/application scenarios, key companies, competitive positions,
regulation/policy, supply chain, customer demand, risks, and future trends.

5. Required output structure
Ask Eureka to produce a structured Markdown report with:
- Title
- Executive summary
- Key findings
- Main analysis sections
- Tables where comparison helps
- Opportunities and risks
- Actionable recommendations
- Open questions or follow-up research directions
- Source/evidence notes when available

6. Quality bar
Ask Eureka to avoid unsupported claims, distinguish facts from inference, explain uncertainty,
prefer recent and authoritative information, and make the final report useful for business
decision-making.

7. Output constraints
Ask Eureka to write the final report in clear Chinese, with concise headings, readable tables,
and no irrelevant filler.
"""


def build_prompt_repair_prompt(state: Mapping[str, Any], raw_response: str) -> str:
    output_schema = prompt_generation_output_schema()

    return f"""The previous response was not valid JSON.

Convert it into valid JSON that matches this schema exactly:
{json.dumps(output_schema, ensure_ascii=False, indent=2)}

Topic:
{state.get("topic", "")}

Previous response:
{raw_response}

Rules:
- Return JSON only.
- Do not wrap the JSON in Markdown fences.
- If a field is missing, infer the best value from the topic and previous response.
- Use only enum values from the schema.
- The prompt field must contain the full Eureka report-generation prompt.
"""


def build_article_metadata_extraction_prompt(state: Mapping[str, Any]) -> str:
    context = state.get("request_context") or {}
    article = (
        state.get("article")
        or state.get("article_text")
        or state.get("content")
        or state.get("markdown")
        or ""
    )
    output_schema = article_metadata_extraction_schema()

    return f"""{ARTICLE_EXTRACTION_SYSTEM_INSTRUCTIONS}

Article:
{article}

Context JSON:
{json.dumps(context, ensure_ascii=False, indent=2)}

Output JSON schema:
{json.dumps(output_schema, ensure_ascii=False, indent=2)}

Return valid JSON only. Do not wrap it in Markdown fences.

Field requirements:
- title: extract the article's original title if present. If no title is present, infer a concise,
  searchable title from the article content.
- categories: classify the article into one or more content types from the categories enum. Prefer
  one primary category unless the article clearly combines multiple formats.
- keywords: extract concrete technologies, products, materials, companies, applications, markets,
  or problem keywords from the article. Avoid broad filler words. Target 5-12 keywords when enough
  evidence exists.
- description: write a one to two sentence Chinese abstract of what the article says and why it is
  useful.
- role: choose the primary user role that would benefit from this article, using only the role enum.
- industry: choose the best industry enum value based on the article evidence.
- jtbd: choose the jobs-to-be-done that the article helps with, using only the jtbd enum.
- date: extract the article's publication or event date and normalize it to YYYY-MM-DD. If the
  article has no usable date, use today's date: {today_iso()}.
- sub_industry: choose relevant sub_industry enum values. Prefer sub-industries that belong to the
  selected industry when possible.

Classification rules:
- Use enum values exactly as they appear in the schema; do not use display names or translations.
- Base extraction on the article. Infer classification fields only when the article gives enough
  evidence.
- If evidence is weak, choose the closest enum value and keep the description conservative.
- Return arrays for categories, keywords, jtbd, and sub_industry even when there is only one item.
"""

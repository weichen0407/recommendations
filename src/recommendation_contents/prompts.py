"""Prompt builders for recommendation content generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .dates import today_iso
from .schemas import prompt_generation_output_schema

SYSTEM_INSTRUCTIONS = """You are a senior prompt engineer for Eureka research/report generation.
Expand the user's short topic into a structured report record and a complete, task-ready prompt
for Eureka. Do not answer the topic itself."""


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

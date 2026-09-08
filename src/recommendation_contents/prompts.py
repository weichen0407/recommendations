"""Prompt builders for recommendation content generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SYSTEM_INSTRUCTIONS = """You are a senior prompt engineer for Eureka research/report generation.
Expand the user's short topic into a complete, task-ready prompt for Eureka.
Do not answer the topic itself. Only write the prompt that Eureka should execute."""


def build_prompt_generation_prompt(state: Mapping[str, Any]) -> str:
    context = state.get("request_context") or {}

    return f"""{SYSTEM_INSTRUCTIONS}

Topic:
{state.get("topic", "")}

Context JSON:
{json.dumps(context, ensure_ascii=False, indent=2)}

Write a complete report-generation prompt in Chinese unless the context explicitly asks for
another language. Keep the generated prompt concise and complete: target 800-1400 Chinese
characters, and do not stop mid-sentence.

The generated prompt must be directly executable by Eureka and should include these parts
without over-expanding any single section:

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

Return plain text only. Do not wrap it in Markdown fences.
"""

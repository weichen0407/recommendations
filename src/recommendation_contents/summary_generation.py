"""Compatibility imports for the former stage-two module name.

New code should import :mod:`recommendation_contents.research_prompt_generation`.
"""

from .research_prompt_generation import (
    HTML_INSTRUCTION,
    RESEARCH_PROMPT_RULES,
    GenerationError,
    build_task_spec,
    generate_research_prompt_specs,
    research_prompt_response_schema,
    validate_research_prompts,
)

# Public aliases retained for callers that used the old terminology.
SUMMARY_RULES = RESEARCH_PROMPT_RULES
generate_task_specs = generate_research_prompt_specs
summary_response_schema = research_prompt_response_schema
validate_summaries = validate_research_prompts

__all__ = [
    "HTML_INSTRUCTION",
    "RESEARCH_PROMPT_RULES",
    "SUMMARY_RULES",
    "GenerationError",
    "build_task_spec",
    "generate_research_prompt_specs",
    "generate_task_specs",
    "research_prompt_response_schema",
    "summary_response_schema",
    "validate_research_prompts",
    "validate_summaries",
]

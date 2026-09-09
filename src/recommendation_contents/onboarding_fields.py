"""Map internal taxonomy values to Onboarding storage values."""

from __future__ import annotations

from typing import Any

ROLE_VALUE_MAP = {
    "rd_engineer_inventor": "rd_engineer",
    "researcher_scientist": "researcher",
    "innovation_product_strategy": "innovation_product_strategy",
    "in_house_ip_legal": "in_house_ip_legal",
    "patent_ip_services": "patent_ip_services",
    "other": "other",
}

INDUSTRY_VALUE_MAP = {
    "medical_devices": "medical_devices",
    "materials": "materials",
    "automotive": "automotive",
    "electronics_manufacturing": "electronics_manufacturing",
    "engineering": "engineering",
    "biotechnology": "biotech",
    "biotech": "biotech",
    "food": "food_farming_production",
    "farming_production": "food_farming_production",
    "food_farming_production": "food_farming_production",
    "energy": "energy",
    "chemical": "chemical",
    "construction": "construction",
    "other": "other",
}

JTBD_VALUE_MAP = {
    "find_technical_solutions": "technical_solutions",
    "explore_existing_technologies": "existing_technologies",
    "generate_product_ideas": "product_ideas",
    "assess_technical_feasibility": "technical_feasibility",
    "assess_patent_and_ip_risk": "patent_ip_risk",
    "explore_new_research_fields": "new_research_fields",
    "find_research_methods": "research_methods",
    "track_research_trends": "research_trends",
    "generate_research_ideas": "research_ideas",
    "search_patents_and_literature": "patents_literature",
    "track_technologies_and_competitors": "technology_competitors",
    "identify_innovation_opportunities": "innovation_opportunities",
    "evaluate_r_and_d_directions": "rd_directions",
    "explore_patent_landscapes": "patent_landscapes",
    "assess_product_ip_risks": "product_ip_risks",
    "search_prior_art_assess_novelty": "prior_art",
    "check_fto_and_design_risks": "fto_design_risks",
    "draft_and_review_patents": "draft_review_patents",
    "respond_to_office_actions": "office_actions",
    "conduct_fto_searches": "fto_searches",
    "draft_and_review_applications": "draft_review_applications",
    "draft_and_refine_claims": "draft_refine_claims",
    "track_technology_trends": "technology_trends",
    "generate_ideas_and_concepts": "ideas_concepts",
    "search_or_draft_patents": "search_draft_patents",
    "other": "other",
}


def onboarding_role_value(value: Any) -> str:
    return _mapped_string(value, ROLE_VALUE_MAP)


def onboarding_industry_value(value: Any) -> str:
    return _mapped_string(value, INDUSTRY_VALUE_MAP)


def onboarding_jtbd_values(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [_mapped_string(value, JTBD_VALUE_MAP) for value in values if _string(value)]


def _mapped_string(value: Any, mapping: dict[str, str]) -> str:
    text = _string(value)
    return mapping.get(text, text)


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""

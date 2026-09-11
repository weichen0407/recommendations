import copy
import json
from pathlib import Path

from recommendation_contents.brief_schema import load_brief_catalog
from recommendation_contents.profile_topic_generation import (
    _focused_catalog,
    _profile_messages,
    all_profile_triples,
    build_profile_topic_schema,
    default_profile_tag_bundle,
    validate_profile_briefs,
    validate_profile_request,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIENCE = {
    "role": "rd_engineer",
    "industry": "electronics_manufacturing",
    "jtbd": "technical_solutions",
}
TAG_BUNDLE = {
    "role_perspective": "product_design",
    "industry_segment": None,
    "jtbd_task": "solution_comparison",
    "desired_output": "comparison_matrix",
    "topic_theme": "ai_impact",
    "question_intent": "identify_applications",
    "scope_level": "industry",
}


def payload():
    documented = json.loads(
        (ROOT / "docs/recommendation-tags/v2/example-chip-interconnect-variants.json").read_text()
    )
    first = documented["briefs"][0]
    result = []
    for index in range(2):
        brief = copy.deepcopy(first)
        brief["title"] = f"AI 在电子制造行业有哪些值得关注的应用方向 {index + 1}？"
        brief["description"] = (
            f"从产品设计视角识别 AI 在电子制造行业第 {index + 1} 类应用方向，形成统一口径的对比矩阵。"
        )
        brief["audience"] = dict(AUDIENCE)
        brief["tags"] = copy.deepcopy(TAG_BUNDLE)
        brief["classification"]["industry_status"] = "broad_scope"
        result.append(brief)
    return {"briefs": result}


def test_current_role_jtbd_mapping_creates_396_unique_triples():
    triples = all_profile_triples()
    assert len(triples) == len({tuple(row.values()) for row in triples}) == 396


def test_default_bundle_adds_theme_intent_and_scope_to_audience_triple():
    catalog = load_brief_catalog()
    bundle = default_profile_tag_bundle(catalog, AUDIENCE)
    assert set(bundle) == set(TAG_BUNDLE)
    assert bundle["topic_theme"] == "ai_impact"
    assert bundle["question_intent"] == "identify_applications"
    assert bundle["scope_level"] == "industry"


def test_profile_briefs_must_preserve_the_whole_fixed_tag_bundle():
    catalog = _focused_catalog(load_brief_catalog(), AUDIENCE, TAG_BUNDLE)
    assert validate_profile_briefs(payload(), catalog, 2, AUDIENCE, TAG_BUNDLE) == []

    invalid = copy.deepcopy(payload())
    invalid["briefs"][0]["tags"]["question_intent"] = "scan_trends"
    errors = validate_profile_briefs(invalid, catalog, 2, AUDIENCE, TAG_BUNDLE)
    assert any("question_intent" in error or "tag_bundle" in error for error in errors)


def test_profile_request_rejects_inconsistent_scope_and_theme_intent():
    inconsistent_scope = {
        **TAG_BUNDLE,
        "industry_segment": "semiconductors",
    }
    _, _, errors = validate_profile_request(
        {"audience": AUDIENCE, "tag_bundle": inconsistent_scope}
    )
    assert any("scope_level" in error for error in errors)

    inconsistent_intent = {**TAG_BUNDLE, "question_intent": "explain_concept"}
    _, _, errors = validate_profile_request(
        {"audience": AUDIENCE, "tag_bundle": inconsistent_intent}
    )
    assert any("question_intent" in error for error in errors)


def test_partial_overrides_fill_dependent_intent_and_scope():
    _, bundle, errors = validate_profile_request(
        {
            "audience": AUDIENCE,
            "tag_overrides": {
                "industry_segment": "semiconductors",
                "topic_theme": "technical_challenges",
            },
        }
    )
    assert errors == []
    assert bundle["scope_level"] == "industry_segment"
    assert bundle["question_intent"] == "identify_challenges"


def test_removed_industry_third_level_is_rejected():
    catalog = load_brief_catalog()
    assert [row["value"] for row in catalog["scope_levels"]] == [
        "industry",
        "industry_segment",
    ]
    _, _, errors = validate_profile_request(
        {
            "audience": AUDIENCE,
            "tag_overrides": {"technology_object": ["chip_interconnect"]},
        }
    )
    assert errors == ["tag_overrides contains unsupported fields"]


def test_profile_schema_matches_exported_artifact():
    exported = json.loads(
        (ROOT / "src/recommendation_contents/data/profile_topic.schema.json").read_text()
    )
    assert build_profile_topic_schema() == exported
    tags = exported["properties"]["briefs"]["items"]["properties"]["tags"]
    assert set(tags["required"]) == set(TAG_BUNDLE)


def test_profile_prompt_fixes_all_facets_and_keeps_keywords_free():
    catalog = _focused_catalog(load_brief_catalog(), AUDIENCE, TAG_BUNDLE)
    request = {
        "audience": AUDIENCE,
        "tag_bundle": TAG_BUNDLE,
        "language": "zh-CN",
        "count": 10,
    }
    messages = _profile_messages(request, catalog, None, [])
    system = messages[0]["content"]
    assert "Copy the input tag_bundle exactly" in system
    assert "Use entities/keywords as free text" in system
    assert "technology_object" not in system
    assert '"question_intent"' in system
    assert '"scope_level"' in system

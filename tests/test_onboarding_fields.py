from recommendation_contents.onboarding_fields import (
    onboarding_industry_value,
    onboarding_jtbd_values,
    onboarding_role_value,
)


def test_onboarding_field_values_match_storage_mapping():
    assert onboarding_role_value("rd_engineer_inventor") == "rd_engineer"
    assert onboarding_role_value("innovation_product_strategy") == "innovation_product_strategy"

    assert onboarding_industry_value("biotechnology") == "biotech"
    assert onboarding_industry_value("food") == "food_farming_production"
    assert onboarding_industry_value("farming_production") == "food_farming_production"

    assert onboarding_jtbd_values(
        [
            "track_technologies_and_competitors",
            "identify_innovation_opportunities",
            "evaluate_r_and_d_directions",
        ]
    ) == ["technology_competitors", "innovation_opportunities", "rd_directions"]


def test_onboarding_mapping_passes_through_already_mapped_values():
    assert onboarding_role_value("researcher") == "researcher"
    assert onboarding_industry_value("biotech") == "biotech"
    assert onboarding_jtbd_values(["technology_competitors"]) == ["technology_competitors"]

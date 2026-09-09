from recommendation_contents.prompts import build_article_metadata_extraction_prompt


def test_build_article_metadata_extraction_prompt_contains_article_and_schema():
    prompt = build_article_metadata_extraction_prompt(
        {
            "article": "标题：手机电池为什么冬天掉电快？文章讨论低温下锂离子电池内阻升高。",
            "request_context": {"language": "zh-CN"},
        }
    )

    assert "手机电池为什么冬天掉电快" in prompt
    assert "Return valid JSON only" in prompt
    assert '"title"' in prompt
    assert '"categories"' in prompt
    assert '"prompt"' not in prompt
    assert "YYYY-MM-DD" in prompt

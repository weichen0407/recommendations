from recommendation_contents.records import read_csv_rows, save_result_table


def test_save_result_table_appends_csv_and_regenerates_markdown(tmp_path):
    csv_path = tmp_path / "records.csv"
    markdown_path = tmp_path / "records.md"

    save_result_table(
        row={
            "input": "主题一",
            "generated_prompt": "提示词一",
            "session_url": "https://example.test/session-1",
            "share_url": "https://example.test/share-1",
            "title": "标题一",
            "categories": "[\"scout_report\"]",
            "keywords": "[\"关键词一\"]",
            "description": "摘要一",
            "role": "innovation_product_strategy",
            "industry": "automotive",
            "jtbd": "[\"identify_innovation_opportunities\"]",
            "date": "2026-09-08",
            "sub_industry": "[\"ev_and_battery_systems\"]",
        },
        csv_path=str(csv_path),
        markdown_path=str(markdown_path),
    )
    save_result_table(
        row={
            "input": "主题二",
            "generated_prompt": "提示词二\n第二行",
            "session_url": "https://example.test/session-2",
            "share_url": "https://example.test/share-2",
            "title": "标题二",
            "categories": "[\"case\"]",
            "keywords": "[\"关键词二\"]",
            "description": "摘要二",
            "role": "rd_engineer_inventor",
            "industry": "energy",
            "jtbd": "[\"find_technical_solutions\"]",
            "date": "2026-09-08",
            "sub_industry": "[\"batteries_and_storage\"]",
        },
        csv_path=str(csv_path),
        markdown_path=str(markdown_path),
    )

    rows = read_csv_rows(str(csv_path))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert [row["input"] for row in rows] == ["主题一", "主题二"]
    assert "提示词二<br>第二行" in markdown
    assert "scout_report" in markdown
    assert "share_url" in markdown


def test_save_result_table_migrates_legacy_headers(tmp_path):
    csv_path = tmp_path / "records.csv"
    markdown_path = tmp_path / "records.md"
    csv_path.write_text(
        "输入,generate prompt 后的 prompt,session 会话链接,最终分享链接\n"
        "旧主题,旧提示词,https://example.test/session-old,https://example.test/share-old\n",
        encoding="utf-8",
    )

    save_result_table(
        row={
            "input": "新主题",
            "generated_prompt": "新提示词",
            "session_url": "https://example.test/session-new",
            "share_url": "https://example.test/share-new",
            "title": "新标题",
        },
        csv_path=str(csv_path),
        markdown_path=str(markdown_path),
    )

    rows = read_csv_rows(str(csv_path))

    assert rows[0]["input"] == "旧主题"
    assert rows[0]["generated_prompt"] == "旧提示词"
    assert rows[0]["session_url"] == "https://example.test/session-old"
    assert rows[1]["input"] == "新主题"

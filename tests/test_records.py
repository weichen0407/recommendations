from recommendation_contents.records import read_csv_rows, save_result_table


def test_save_result_table_appends_csv_and_regenerates_markdown(tmp_path):
    csv_path = tmp_path / "records.csv"
    markdown_path = tmp_path / "records.md"

    save_result_table(
        row={
            "输入": "主题一",
            "generate prompt 后的 prompt": "提示词一",
            "session 会话链接": "https://example.test/session-1",
            "最终分享链接": "https://example.test/share-1",
        },
        csv_path=str(csv_path),
        markdown_path=str(markdown_path),
    )
    save_result_table(
        row={
            "输入": "主题二",
            "generate prompt 后的 prompt": "提示词二\n第二行",
            "session 会话链接": "https://example.test/session-2",
            "最终分享链接": "https://example.test/share-2",
        },
        csv_path=str(csv_path),
        markdown_path=str(markdown_path),
    )

    rows = read_csv_rows(str(csv_path))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert [row["输入"] for row in rows] == ["主题一", "主题二"]
    assert "提示词二<br>第二行" in markdown
    assert "最终分享链接" in markdown

from agent.output_sanitizer import sanitize_model_output


def test_sanitize_model_output_removes_citations_urls_and_unapproved_markup():
    text = sanitize_model_output(
        "<b>标题</b>\n**AAPL** [[1]](https://example.com) <div>x</div> https://example.com 🟡"
    )

    assert "<b>标题</b>" in text
    assert "AAPL" in text
    assert "**" not in text
    assert "[[1]]" not in text
    assert "https://" not in text
    assert "<div>" not in text
    assert "🟡" not in text
    assert "⚪" in text

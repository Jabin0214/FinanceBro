from bot.messaging import TELEGRAM_TEXT_LIMIT, split_long


def test_split_long_breaks_single_oversized_paragraph():
    text = "x" * (TELEGRAM_TEXT_LIMIT * 2 + 17)

    chunks = split_long(text)

    assert "".join(chunks) == text
    assert all(len(chunk) <= TELEGRAM_TEXT_LIMIT for chunk in chunks)


def test_split_long_preserves_paragraph_boundaries_when_possible():
    text = "first\n\nsecond"

    assert split_long(text, limit=20) == [text]

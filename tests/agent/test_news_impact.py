from agent.news_impact import (
    extract_mentioned_symbols,
    polarity_score,
    score_headline,
    rank_news_by_impact,
)


def test_extract_mentioned_symbols_uppercase_word_boundary():
    text = "AAPL beats earnings; TSLA misses; aapl rumor (lowercase ignored)"
    symbols = {"AAPL", "TSLA", "MSFT"}
    assert extract_mentioned_symbols(text, symbols) == {"AAPL", "TSLA"}


def test_extract_mentioned_symbols_handles_punctuation():
    text = "$NVDA up 5%, GOOG/L flat."
    symbols = {"NVDA", "GOOG", "GOOGL"}
    found = extract_mentioned_symbols(text, symbols)
    assert "NVDA" in found
    assert "GOOG" in found


def test_polarity_positive_keywords():
    assert polarity_score("beats earnings, raises guidance") > 0


def test_polarity_negative_keywords():
    assert polarity_score("misses earnings, downgrade, lawsuit") < 0


def test_polarity_neutral():
    assert polarity_score("reports quarterly results") == 0


def test_score_headline_combines_weight_and_polarity():
    weights = {"AAPL": 20.0, "TSLA": 5.0}
    score = score_headline(
        "AAPL beats earnings and raises guidance",
        symbols=set(weights),
        weights=weights,
    )
    assert score["impact"] > 0
    assert score["symbols"] == ["AAPL"]
    assert score["polarity"] > 0


def test_score_headline_ignores_unweighted_mentions():
    weights = {"AAPL": 20.0}
    score = score_headline(
        "TSLA recall announced",
        symbols={"AAPL", "TSLA"},
        weights=weights,
    )
    assert score["impact"] == 0
    assert score["symbols"] == ["TSLA"]


def test_rank_news_by_impact_sorts_descending_abs():
    weights = {"AAPL": 20.0, "TSLA": 5.0}
    items = [
        "TSLA recall announced",
        "AAPL beats earnings",
        "MSFT launches new product",
    ]
    ranked = rank_news_by_impact(items, weights=weights)
    assert ranked[0]["headline"] == "AAPL beats earnings"
    assert ranked[1]["headline"] == "TSLA recall announced"
    assert ranked[2]["headline"] == "MSFT launches new product"

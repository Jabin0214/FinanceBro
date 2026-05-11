"""Score news items by portfolio impact (mentioned tickers × position weight × polarity).

Lightweight, deterministic, no LLM calls. The Grok narrative still drives the
prose summary; this module is purely for ranking and routing.
"""

from __future__ import annotations

import re

_POSITIVE = {
    "beats", "beat", "raises", "raise", "upgrade", "upgraded", "record",
    "strong", "outperform", "surge", "surges", "rally", "rallies",
    "breakthrough", "approval", "approved", "win", "wins", "partnership",
}
_NEGATIVE = {
    "misses", "miss", "downgrade", "downgraded", "lawsuit", "investigation",
    "recall", "warns", "warning", "cut", "cuts", "slump", "plunge", "plunges",
    "halt", "halted", "fraud", "delisting", "bankruptcy", "decline", "declines",
}

_TOKEN_RE = re.compile(r"[A-Z]{1,6}")


def extract_mentioned_symbols(text: str, symbols: set[str]) -> set[str]:
    """Return the subset of `symbols` that appear as uppercase word tokens in text."""
    found = set(_TOKEN_RE.findall(text))
    return found & symbols


def polarity_score(text: str) -> int:
    """Naive polarity: +1 per positive keyword, -1 per negative keyword."""
    words = {w.strip(".,;:!?()[]\"'$/%").lower() for w in text.split()}
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    return pos - neg


def score_headline(
    headline: str,
    symbols: set[str],
    weights: dict[str, float],
) -> dict:
    """Score one headline.

    Returns {headline, symbols, polarity, impact} where impact = sum(weight_of_symbol)
    * polarity. Mentioned-but-unheld symbols are listed but contribute zero weight.
    """
    mentioned = extract_mentioned_symbols(headline, symbols)
    pol = polarity_score(headline)
    weight = sum(weights.get(s, 0.0) for s in mentioned)
    return {
        "headline": headline,
        "symbols": sorted(mentioned),
        "polarity": pol,
        "impact": round(weight * pol, 2),
    }


def rank_news_by_impact(
    headlines: list[str],
    weights: dict[str, float],
) -> list[dict]:
    """Return scored headlines sorted by |impact| descending."""
    symbols = set(weights)
    scored = [score_headline(h, symbols, weights) for h in headlines]
    scored.sort(key=lambda x: abs(x["impact"]), reverse=True)
    return scored

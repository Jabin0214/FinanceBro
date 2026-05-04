from types import SimpleNamespace

from agent import scout


def _portfolio():
    return {
        "accounts": [
            {
                "positions": [
                    {"symbol": "AAPL", "market_value_base": 6000.0},
                    {"symbol": "MSFT", "market_value_base": 4000.0},
                ]
            }
        ]
    }


def test_analyze_watchlist_searches_watchlist_and_current_holdings(monkeypatch):
    captured = {}

    class FakeResponse:
        text = ""
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "<b>候选观察</b>\nAAPL 继续观察。"}
                        ],
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(scout, "GROK_API_KEY", "key")
    monkeypatch.setattr(scout.requests, "post", fake_post)

    result = scout.analyze_watchlist(
        [{"symbol": "NVDA", "note": "AI infra"}, {"symbol": "AAPL", "note": ""}],
        _portfolio(),
    )

    assert "<b>候选观察</b>" in result
    assert captured["payload"]["model"] == scout.SCOUT_MODEL
    assert captured["payload"]["tools"] == [{"type": "web_search"}, {"type": "x_search"}]
    user_prompt = captured["payload"]["input"][1]["content"]
    assert "NVDA" in user_prompt
    assert "AI infra" in user_prompt
    assert "当前已持仓" in user_prompt
    assert "MSFT" in user_prompt


def test_analyze_watchlist_requires_items(monkeypatch):
    result = scout.analyze_watchlist([], _portfolio())

    assert "观察列表为空" in result


def test_analyze_watchlist_sanitizes_model_output(monkeypatch):
    class FakeResponse:
        text = ""
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "<b>候选观察</b>\n**AAPL** [[1]](https://example.com) https://example.com",
                            }
                        ],
                    }
                ]
            }

    monkeypatch.setattr(scout, "GROK_API_KEY", "key")
    monkeypatch.setattr(scout.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = scout.analyze_watchlist([{"symbol": "AAPL", "note": ""}], _portfolio())

    assert "<b>候选观察</b>" in result
    assert "AAPL" in result
    assert "**" not in result
    assert "[[1]]" not in result
    assert "https://" not in result

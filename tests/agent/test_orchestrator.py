from types import SimpleNamespace

import pytest

from agent import orchestrator


class _ToolUseBlock:
    type = "tool_use"
    name = "get_portfolio"
    input = {}
    id = "toolu_1"

    def model_dump(self):
        return {
            "type": self.type,
            "name": self.name,
            "input": self.input,
            "id": self.id,
        }


class _LoopingMessages:
    def __init__(self):
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[_ToolUseBlock()],
            usage=SimpleNamespace(
                input_tokens=1,
                output_tokens=1,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


def test_chat_stops_after_tool_loop_limit(monkeypatch):
    messages = _LoopingMessages()
    monkeypatch.setattr(orchestrator, "_get_client", lambda: SimpleNamespace(messages=messages))
    monkeypatch.setattr(orchestrator, "execute_tool", lambda _name, _input: "{}")

    with pytest.raises(RuntimeError, match="工具调用次数过多"):
        orchestrator.chat([], "看看持仓")

    assert messages.calls == orchestrator.MAX_TOOL_ROUNDS

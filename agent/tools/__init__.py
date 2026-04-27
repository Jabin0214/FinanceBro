"""Tool registry for the Orchestrator agent.

Each tool lives in its own module with a `DEFINITION` (Anthropic schema)
and an `execute(tool_input) -> str`. Adding a tool is a two-line change
in `_TOOLS` below.
"""

from agent.tools import news, portfolio, report, risk
from agent.tools._state import (
    pop_pending_files,
    reset_active_user,
    set_active_user,
)

__all__ = [
    "TOOL_DEFINITIONS",
    "execute_tool",
    "set_active_user",
    "reset_active_user",
    "pop_pending_files",
]

_TOOLS = {
    portfolio.DEFINITION["name"]: portfolio.execute,
    report.DEFINITION["name"]:    report.execute,
    news.DEFINITION["name"]:      news.execute,
    risk.DEFINITION["name"]:      risk.execute,
}

TOOL_DEFINITIONS = [
    portfolio.DEFINITION,
    report.DEFINITION,
    news.DEFINITION,
    risk.DEFINITION,
]


def execute_tool(name: str, tool_input: dict) -> str:
    if name not in _TOOLS:
        raise ValueError(f"未知工具: {name}")
    return _TOOLS[name](tool_input)

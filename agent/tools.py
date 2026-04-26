"""
工具注册表 — Claude tool use

每个工具包含两部分：
  1. TOOL_DEFINITIONS 里的 schema（告诉 Claude 工具的用途和参数）
  2. execute_tool() 里的执行逻辑（实际调用 Python 函数）

新增工具时只需：
  - 在 TOOL_DEFINITIONS 追加一条 schema
  - 在 execute_tool() 追加对应的 elif 分支
"""

import json
import logging
import tempfile
import os
import time
from contextvars import ContextVar
from uuid import uuid4

logger = logging.getLogger(__name__)

# 持仓数据本地缓存
_portfolio_cache: dict | None = None
_portfolio_cache_ts: float = 0.0
_PORTFOLIO_CACHE_TTL = 600  # 10 分钟

# 新闻缓存（query → (结果, 时间戳)）
_news_cache: dict[str, tuple[str, float]] = {}
_NEWS_CACHE_TTL = 300  # 5 分钟

# 待发送文件队列（按 user_id 隔离，由 bot 层在每次 chat() 后消费）
_pending_files: dict[int, list[dict]] = {}
_active_user_id: ContextVar[int | None] = ContextVar("active_user_id", default=None)

# ── 工具 Schema（发给 Claude） ─────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_portfolio",
        "description": (
            "获取 IBKR 账户的最新实时持仓数据，包括账户净值、现金余额、"
            "各持仓的市值、成本、浮动盈亏等信息。"
            "用于回答用户关于持仓、盈亏、账户状况等问题，以文字形式分析和回复。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_realtime_account_snapshot",
        "description": (
            "通过 IB Gateway 获取实时账户快照，包括总净值、可用现金、"
            "当前股票持仓、持仓数量和平均成本。"
            "当用户询问当前实时持仓、实时现金、实时净值、当前有多少股某标的时调用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "generate_report",
        "description": (
            "生成完整的 IBKR 持仓 HTML 报表文件并发送给用户。"
            "当用户明确要求报表、报告文件、完整持仓表格时调用。"
            "与 get_portfolio 的区别：此工具发送可下载的 HTML 文件，而不是文字回复。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_news",
        "description": (
            "搜索最新财经新闻和 X（Twitter）上的实时市场讨论。"
            "适用场景：某只股票/公司的最新动态、大盘行情、宏观经济事件、行业趋势、"
            "今日市场概况等。只要用户问到任何与新闻、市场动态、最新消息相关的问题都应调用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，可以是股票代码、公司名、宏观主题（如 'Fed interest rate'、'AI stocks today'、'今日美股'）等",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_risk_analysis",
        "description": (
            "对整体持仓进行深度风险评估，包括集中度分析、板块分布、币种敞口、"
            "盈亏分布，并结合实时市场动态给出风险建议。"
            "当用户询问风险、仓位安全性、是否过度集中、投资组合健康度等问题时调用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_option_chain",
        "description": (
            "通过 IB Gateway 查询指定标的的实时/延迟期权链，"
            "返回到期日、行权价、bid/ask、delta、IV、OI、volume 等字段。"
            "当用户询问某只股票的期权数据、IV、期权报价、期权链时调用。"
            "需要 IB Gateway 正在运行。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "美股/ETF 代码，如 'AAPL'、'SPY'、'QQQ'",
                },
                "dte_min": {
                    "type": "integer",
                    "description": "最小到期天数（默认 0）",
                },
                "dte_max": {
                    "type": "integer",
                    "description": "最大到期天数（默认 60）",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "scan_short_put_candidates",
        "description": (
            "筛选适合卖出的 cash-secured put 候选合约，"
            "按 DTE、|delta|、权利金、OI、volume 过滤，结果按年化收益率排序。"
            "当用户询问能卖哪些 put、cash-secured put 策略、卖 put 赚权利金时调用。"
            "需要 IB Gateway 正在运行。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "美股/ETF 代码",
                },
                "dte_min": {
                    "type": "integer",
                    "description": "最小 DTE（默认 20）",
                },
                "dte_max": {
                    "type": "integer",
                    "description": "最大 DTE（默认 45）",
                },
                "delta_min": {
                    "type": "number",
                    "description": "最小 |delta|（默认 0.15）",
                },
                "delta_max": {
                    "type": "number",
                    "description": "最大 |delta|（默认 0.30）",
                },
                "min_oi": {
                    "type": "integer",
                    "description": "最低未平仓量 OI（默认 100）",
                },
                "min_volume": {
                    "type": "integer",
                    "description": "最低当日成交量（默认 10）",
                },
                "min_premium": {
                    "type": "number",
                    "description": "最低权利金（默认 0.10 美元）",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "scan_covered_call_candidates",
        "description": (
            "筛选适合卖出的 covered call 候选合约，"
            "按 DTE、delta、权利金、OI、volume 过滤，结果按年化收益率排序。"
            "当用户询问能卖哪些 covered call、卖 call 增强收益时调用。"
            "⚠️ 裸 call 不在此工具范围内，调用方须持有对应正股。"
            "需要 IB Gateway 正在运行。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "美股/ETF 代码（应已持有该股票正股）",
                },
                "dte_min": {
                    "type": "integer",
                    "description": "最小 DTE（默认 15）",
                },
                "dte_max": {
                    "type": "integer",
                    "description": "最大 DTE（默认 45）",
                },
                "delta_min": {
                    "type": "number",
                    "description": "最小 delta（默认 0.10）",
                },
                "delta_max": {
                    "type": "number",
                    "description": "最大 delta（默认 0.25）",
                },
                "min_oi": {
                    "type": "integer",
                    "description": "最低未平仓量 OI（默认 100）",
                },
                "min_volume": {
                    "type": "integer",
                    "description": "最低当日成交量（默认 10）",
                },
                "min_premium": {
                    "type": "number",
                    "description": "最低权利金（默认 0.10 美元）",
                },
            },
            "required": ["symbol"],
        },
    },
]


# ── 工具执行器 ────────────────────────────────────────────────────────────────

def execute_tool(name: str, tool_input: dict) -> str:
    if name == "get_portfolio":
        return _get_portfolio()
    if name == "get_realtime_account_snapshot":
        return _get_realtime_account_snapshot()
    if name == "generate_report":
        return _generate_report()
    if name == "get_news":
        return _get_news(tool_input["query"])
    if name == "get_risk_analysis":
        return _get_risk_analysis()
    if name == "get_option_chain":
        return _get_option_chain(tool_input)
    if name == "scan_short_put_candidates":
        return _scan_short_put_candidates(tool_input)
    if name == "scan_covered_call_candidates":
        return _scan_covered_call_candidates(tool_input)
    raise ValueError(f"未知工具: {name}")


def set_active_user(user_id: int) -> object:
    """设置当前工具调用所属用户，返回可用于 reset 的 token。"""
    return _active_user_id.set(user_id)


def reset_active_user(token: object) -> None:
    _active_user_id.reset(token)


def pop_pending_files(user_id: int) -> list[dict]:
    """取出并清空指定用户的待发送文件队列，由 bot 层调用。"""
    return _pending_files.pop(user_id, [])


def _get_portfolio() -> str:
    global _portfolio_cache, _portfolio_cache_ts
    from ibkr.flex_query import fetch_flex_report

    now = time.time()
    if _portfolio_cache and now - _portfolio_cache_ts < _PORTFOLIO_CACHE_TTL:
        logger.info("工具调用: get_portfolio — 使用缓存数据（剩余 %.0fs）", _PORTFOLIO_CACHE_TTL - (now - _portfolio_cache_ts))
        return json.dumps(_portfolio_cache, ensure_ascii=False)

    logger.info("工具调用: get_portfolio — 正在从 IBKR 获取数据...")
    data = fetch_flex_report()
    _portfolio_cache = data
    _portfolio_cache_ts = time.time()
    return json.dumps(data, ensure_ascii=False)


def _get_realtime_account_snapshot() -> str:
    from ibkr.account import get_realtime_account_snapshot

    logger.info("工具调用: get_realtime_account_snapshot")
    result = get_realtime_account_snapshot()
    return json.dumps(result, ensure_ascii=False)


def _generate_report() -> str:
    from ibkr.flex_query import fetch_flex_report
    from report.html_report import build_html_file

    logger.info("工具调用: generate_report — 正在生成 HTML 报表...")

    # 优先用缓存，避免重复拉 IBKR
    global _portfolio_cache, _portfolio_cache_ts
    now = time.time()
    if _portfolio_cache and now - _portfolio_cache_ts < _PORTFOLIO_CACHE_TTL:
        data = _portfolio_cache
    else:
        data = fetch_flex_report()
        _portfolio_cache = data
        _portfolio_cache_ts = time.time()

    user_id = _active_user_id.get()
    if user_id is None:
        raise RuntimeError("未设置当前用户，无法安全生成报表")

    report_date = data.get("report_date", "report").replace("-", "")
    unique_suffix = uuid4().hex[:8]
    tmp_path = os.path.join(
        tempfile.gettempdir(),
        f"ibkr_report_{report_date}_{user_id}_{unique_suffix}.html",
    )
    build_html_file(data, tmp_path)

    _pending_files.setdefault(user_id, []).append({
        "path": tmp_path,
        "filename": f"ibkr_report_{report_date}.html",
        "caption": f"📊 IBKR 持仓报告 {data.get('report_date', '')}",
    })

    return "报表已生成，正在发送给你。"


def _get_news(query: str) -> str:
    import requests
    from config import GROK_API_KEY

    logger.info("工具调用: get_news — query=%s", query)

    if not GROK_API_KEY:
        return "错误：未配置 GROK_API_KEY，无法搜索新闻。"

    # 缓存命中
    now = time.time()
    cache_key = query.strip().lower()
    if cache_key in _news_cache:
        cached_result, cached_ts = _news_cache[cache_key]
        if now - cached_ts < _NEWS_CACHE_TTL:
            logger.info("get_news — 缓存命中（剩余 %.0fs）", _NEWS_CACHE_TTL - (now - cached_ts))
            return cached_result

    payload = {
        "model": "grok-4-1-fast-reasoning",
        "input": [
            {
                "role": "system",
                "content": (
                    "你是一个金融新闻助手。请搜索并汇总关于用户查询的最新新闻，"
                    "重点关注：重大公告、财报、监管动态、市场情绪（来自 X/Twitter）。"
                    "用中文输出，结构清晰，每条新闻注明时间（若可知）。"
                ),
            },
            {
                "role": "user",
                "content": f"请搜索关于「{query}」的最新新闻和市场动态。",
            },
        ],
        "tools": [
            {"type": "web_search"},
            {"type": "x_search"},
        ],
    }

    try:
        resp = requests.post(
            "https://api.x.ai/v1/responses",
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # Responses API 返回格式：output 数组，取最后一条 message 的文本
        result = ""
        for item in reversed(data.get("output", [])):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        result = block.get("text", "")
                        break
            if result:
                break

        if not result:
            return "新闻获取失败：返回内容为空"

        _news_cache[cache_key] = (result, time.time())
        return result
    except requests.HTTPError as e:
        logger.error("Grok API 请求失败: %s — %s", e, resp.text)
        return f"新闻获取失败（HTTP {resp.status_code}）：{resp.text[:200]}"
    except Exception as e:
        logger.exception("get_news 执行异常")
        return f"新闻获取失败：{e}"


def run_risk_analysis() -> str:
    """公开入口，供 bot 层 /risk 命令直接调用。"""
    return _get_risk_analysis()


def _get_risk_analysis() -> str:
    from ibkr.flex_query import fetch_flex_report
    from agent.risk_calculator import compute_metrics
    from agent.analyzer import analyze_risk

    logger.info("工具调用: get_risk_analysis — 正在获取持仓数据...")

    global _portfolio_cache, _portfolio_cache_ts
    now = time.time()
    if _portfolio_cache and now - _portfolio_cache_ts < _PORTFOLIO_CACHE_TTL:
        data = _portfolio_cache
    else:
        data = fetch_flex_report()
        _portfolio_cache = data
        _portfolio_cache_ts = time.time()

    metrics = compute_metrics(data)
    if "error" in metrics:
        return f"风险分析失败：{metrics['error']}"

    logger.info("工具调用: get_risk_analysis — 正在调用 Grok 进行风险评估...")
    return analyze_risk(metrics)


def _get_option_chain(tool_input: dict) -> str:
    from ibkr.options import get_option_chain

    symbol = tool_input["symbol"].upper().strip()
    dte_min = int(tool_input.get("dte_min", 0))
    dte_max = int(tool_input.get("dte_max", 60))

    logger.info("工具调用: get_option_chain — symbol=%s dte=%d-%d", symbol, dte_min, dte_max)
    result = get_option_chain(symbol, dte_min=dte_min, dte_max=dte_max)
    return json.dumps(result, ensure_ascii=False)


def _scan_short_put_candidates(tool_input: dict) -> str:
    from ibkr.options import scan_short_put_candidates

    symbol = tool_input["symbol"].upper().strip()
    kwargs = {
        "dte_min":     int(tool_input.get("dte_min", 20)),
        "dte_max":     int(tool_input.get("dte_max", 45)),
        "delta_min":   float(tool_input.get("delta_min", 0.15)),
        "delta_max":   float(tool_input.get("delta_max", 0.30)),
        "min_oi":      int(tool_input.get("min_oi", 100)),
        "min_volume":  int(tool_input.get("min_volume", 10)),
        "min_premium": float(tool_input.get("min_premium", 0.10)),
    }
    logger.info("工具调用: scan_short_put_candidates — symbol=%s params=%s", symbol, kwargs)
    result = scan_short_put_candidates(symbol, **kwargs)
    return json.dumps(result, ensure_ascii=False)


def _scan_covered_call_candidates(tool_input: dict) -> str:
    from ibkr.options import scan_covered_call_candidates

    symbol = tool_input["symbol"].upper().strip()
    kwargs = {
        "dte_min":     int(tool_input.get("dte_min", 15)),
        "dte_max":     int(tool_input.get("dte_max", 45)),
        "delta_min":   float(tool_input.get("delta_min", 0.10)),
        "delta_max":   float(tool_input.get("delta_max", 0.25)),
        "min_oi":      int(tool_input.get("min_oi", 100)),
        "min_volume":  int(tool_input.get("min_volume", 10)),
        "min_premium": float(tool_input.get("min_premium", 0.10)),
    }
    logger.info("工具调用: scan_covered_call_candidates — symbol=%s params=%s", symbol, kwargs)
    result = scan_covered_call_candidates(symbol, **kwargs)
    return json.dumps(result, ensure_ascii=False)

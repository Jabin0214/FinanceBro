"""
将 IBKR 结构化数据格式化为 Telegram HTML 报告。

Telegram HTML 支持的标签：
  <b>粗体</b>  <i>斜体</i>  <code>等宽</code>  <u>下划线</u>
  <s>删除线</s>  <pre>代码块</pre>

Telegram 单条消息上限 4096 字符，超出时需要分段发送。
"""

import logging

logger = logging.getLogger(__name__)

MAX_MSG_LENGTH = 4000  # 留点余量
MAX_POSITIONS = 10


def _pnl_icon(value: float) -> str:
    if value > 0:
        return "🟢"
    if value < 0:
        return "🔴"
    return "⚪"


def _fmt_num(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}"


def _fmt_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _format_account(account: dict) -> str:
    acc_id = account["account_id"]
    alias = account.get("alias", "")
    currency = account["base_currency"]
    s = account["summary"]

    title = f"<b>{acc_id}</b>" + (f"（{alias}）" if alias else "")

    pnl = s["total_unrealized_pnl_base"]
    pnl_pct = s["total_unrealized_pnl_pct"]
    icon = _pnl_icon(pnl)

    overview = (
        f"{title}\n"
        f"净值：<b>{_fmt_num(s['net_liquidation'])} {currency}</b>\n"
        f"现金：{_fmt_num(s['cash_base'])} {currency}\n"
        f"股票市值：{_fmt_num(s['stock_value_base'])} {currency}\n"
        f"浮动盈亏：{icon} {_fmt_num(pnl)} {currency}（{_fmt_pct(pnl_pct)}）"
    )

    positions = account.get("positions", [])
    if not positions:
        return overview

    positions = sorted(positions, key=lambda p: p["market_value_base"], reverse=True)
    total = len(positions)
    shown = positions[:MAX_POSITIONS]

    pos_lines = ["", "<b>持仓明细</b>"]
    for p in shown:
        p_icon = _pnl_icon(p["unrealized_pnl"])
        line = (
            f"{p_icon} <b>{p['symbol']}</b> {p['description']}\n"
            f"   {_fmt_num(p['quantity'], 0)} 股 · "
            f"成本 {_fmt_num(p['cost_price'])} · "
            f"现价 {_fmt_num(p['mark_price'])} {p['currency']}\n"
            f"   市值 {_fmt_num(p['market_value_base'])} {account['base_currency']} · "
            f"盈亏 {_fmt_num(p['unrealized_pnl_base'])} {account['base_currency']}（{_fmt_pct(p['unrealized_pnl_pct'])}）"
        )
        pos_lines.append(line)

    if total > MAX_POSITIONS:
        pos_lines.append(f"<i>…还有 {total - MAX_POSITIONS} 个持仓未显示</i>")

    return overview + "\n".join(pos_lines)


def format_report(data: dict) -> list[str]:
    """
    将 IBKR 数据格式化为 Telegram HTML，返回消息列表（超长时自动分段）。
    """
    logger.info("正在格式化报告...")

    sections = []
    for account in data.get("accounts", []):
        sections.append(_format_account(account))

    sections.append(f"<i>生成时间：{data.get('generated_at', '')}</i>")

    full_text = "\n\n".join(sections)
    return _split_message(full_text)


def _split_message(text: str) -> list[str]:
    """将超长消息按段落切分，每段不超过 MAX_MSG_LENGTH。"""
    if len(text) <= MAX_MSG_LENGTH:
        return [text]

    parts = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= MAX_MSG_LENGTH:
            current = current + ("\n\n" if current else "") + para
        else:
            if current:
                parts.append(current)
            current = para

    if current:
        parts.append(current)

    return parts

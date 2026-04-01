"""
IBKR 持仓报告 → Telegram HTML

纯 Python 生成，无需 AI，快速稳定。
Telegram 支持的 HTML 标签：<b> <i> <code> <u> <s>

用法：
    from agent.html_report import build_report_messages
    messages = build_report_messages(parsed_data)   # 返回 list[str]
"""

from __future__ import annotations

MAX_MSG_LEN = 4000  # Telegram 上限 4096，留余量


# ── 公共入口 ──────────────────────────────────────────────────────────────

def build_report_messages(data: dict) -> list[str]:
    """
    将 parser.parse_flex_xml() 返回的 dict 转为 Telegram HTML 消息列表。
    多个账户各成一段；超过 4000 字符自动分包。
    """
    accounts = data.get("accounts", [])
    generated_at = data.get("generated_at", "")
    report_date = data.get("report_date", "")

    parts: list[str] = []

    # 多账户时在最前面加汇总
    if len(accounts) > 1:
        parts.append(_build_total_summary(accounts, report_date))

    for acct in accounts:
        parts.append(_build_account_section(acct))

    # 时间戳附在最后一条消息
    if parts:
        footer = f"\n<i>报告时间：{generated_at}</i>"
        if len(parts[-1]) + len(footer) <= MAX_MSG_LEN:
            parts[-1] += footer
        else:
            parts.append(footer)

    # 长消息拆包
    result: list[str] = []
    for part in parts:
        result.extend(_split(part))

    return result


# ── 多账户汇总 ────────────────────────────────────────────────────────────

def _build_total_summary(accounts: list[dict], report_date: str) -> str:
    total_net_liq = sum(a["summary"]["net_liquidation"] for a in accounts)
    total_pnl = sum(a["summary"]["total_unrealized_pnl_base"] for a in accounts)
    total_cost = sum(a["summary"]["total_cost_base"] for a in accounts)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    base_ccy = accounts[0]["base_currency"] if accounts else "HKD"

    lines = [
        f"<b>📊 总账户汇总</b>  <code>{report_date}</code>",
        "",
        f"合计净值　{_money(total_net_liq)} {base_ccy}",
        f"合计浮盈　{_pnl_str(total_pnl)} {base_ccy}　{_pct(total_pnl_pct)}",
        "",
    ]
    for acct in accounts:
        s = acct["summary"]
        alias = acct["alias"] or acct["account_id"]
        lines.append(
            f"  • <b>{alias}</b>　净值 {_money(s['net_liquidation'])} {acct['base_currency']}"
        )

    return "\n".join(lines)


# ── 单账户报告 ────────────────────────────────────────────────────────────

def _build_account_section(acct: dict) -> str:
    account_id = acct["account_id"]
    alias = acct["alias"] or account_id
    base_ccy = acct["base_currency"]
    s = acct["summary"]
    positions = acct["positions"]
    cash_balances = acct["cash_balances"]

    lines: list[str] = []

    # ── 标题 ──
    title = f"<b>{alias}</b>" if alias != account_id else f"<b>{account_id}</b>"
    lines += [
        f"{'━' * 20}",
        f"{title}  <code>{account_id}</code>",
        "",
    ]

    # ── 账户概览 ──
    lines += [
        "<b>账户概览</b>",
        f"净值　　{_money(s['net_liquidation'])} {base_ccy}",
        f"股票市值  {_money(s['stock_value_base'])} {base_ccy}",
        f"现金　　{_money(s['cash_base'])} {base_ccy}",
        f"浮动盈亏  {_pnl_str(s['total_unrealized_pnl_base'])} {base_ccy}　{_pct(s['total_unrealized_pnl_pct'])}",
        "",
    ]

    # ── 持仓明细 ──
    if positions:
        lines.append("<b>持仓明细</b>")
        for pos in positions:
            lines.append(_build_position_line(pos, base_ccy))
        lines.append("")
    else:
        lines += ["<i>暂无持仓</i>", ""]

    # ── 现金余额 ──
    if cash_balances:
        lines.append("<b>现金余额</b>")
        for cb in cash_balances:
            lines.append(
                f"  {cb['currency']}　{_money(cb['ending_cash'])}　"
                f"≈ {_money(cb['ending_cash_base'])} {base_ccy}"
            )

    return "\n".join(lines)


def _build_position_line(pos: dict, base_ccy: str) -> str:
    symbol = pos["symbol"]
    desc = _truncate(pos["description"], 16)
    currency = pos["currency"]
    qty = int(pos["quantity"]) if pos["quantity"] == int(pos["quantity"]) else pos["quantity"]
    mark = pos["mark_price"]
    mv = pos["market_value"]
    mv_base = pos["market_value_base"]
    pnl = pos["unrealized_pnl"]
    pnl_pct = pos["unrealized_pnl_pct"]
    fx = pos["fx_rate"]

    indicator = _pnl_indicator(pnl)

    # 跨币种时同时显示本币和折算后基础货币
    if currency != base_ccy and fx != 1.0:
        mv_str = f"{_money(mv)} {currency}　≈ {_money(mv_base)} {base_ccy}"
        pnl_str = f"{_pnl_str(pnl)} {currency}"
    else:
        mv_str = f"{_money(mv)} {base_ccy}"
        pnl_str = f"{_pnl_str(pnl)} {base_ccy}"

    return (
        f"{indicator} <b>{symbol}</b> <i>{desc}</i>\n"
        f"     {qty}股 @ {mark}　市值 {mv_str}\n"
        f"     浮盈 {pnl_str}　{_pct(pnl_pct)}"
    )


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _money(value: float) -> str:
    """格式化金额，千位分隔符，两位小数。"""
    return f"{value:,.2f}"


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"({sign}{value:.2f}%)"


def _pnl_str(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f}"


def _pnl_indicator(value: float) -> str:
    if value > 0:
        return "🟢"
    elif value < 0:
        return "🔴"
    return "⚪"


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[:max_len - 1] + "…"


def _split(text: str) -> list[str]:
    """将超长文本按段落切分，每段不超过 MAX_MSG_LEN。"""
    if len(text) <= MAX_MSG_LEN:
        return [text]

    parts = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate) <= MAX_MSG_LEN:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = para

    if current:
        parts.append(current)

    return parts or [text[:MAX_MSG_LEN]]


# ── HTML 文件生成 ─────────────────────────────────────────────────────────

def build_html_file(data: dict, output_path: str) -> str:
    """
    生成完整的 HTML 报告文件，写入 output_path，返回文件路径。
    可在浏览器中打开查看。
    """
    html = _render_html(data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def _render_html(data: dict) -> str:
    accounts = data.get("accounts", [])
    generated_at = data.get("generated_at", "")
    report_date = data.get("report_date", "")

    accounts_html = "\n".join(_render_account(a) for a in accounts)

    total_net = sum(a["summary"]["net_liquidation"] for a in accounts)
    total_pnl = sum(a["summary"]["total_unrealized_pnl_base"] for a in accounts)
    total_cost = sum(a["summary"]["total_cost_base"] for a in accounts)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    base_ccy = accounts[0]["base_currency"] if accounts else "HKD"
    pnl_color = "#26a69a" if total_pnl >= 0 else "#ef5350"
    pnl_sign = "+" if total_pnl >= 0 else ""

    multi_summary = ""
    if len(accounts) > 1:
        account_rows = "".join(
            f"""<tr>
                <td>{a['alias'] or a['account_id']}</td>
                <td>{a['account_id']}</td>
                <td class="num">{_money(a['summary']['net_liquidation'])} {a['base_currency']}</td>
                <td class="num {'green' if a['summary']['total_unrealized_pnl_base'] >= 0 else 'red'}">
                    {pnl_sign if a['summary']['total_unrealized_pnl_base'] >= 0 else ''}{_money(a['summary']['total_unrealized_pnl_base'])}
                    <span class="pct">({'+' if a['summary']['total_unrealized_pnl_pct'] >= 0 else ''}{a['summary']['total_unrealized_pnl_pct']:.2f}%)</span>
                </td>
            </tr>"""
            for a in accounts
        )
        multi_summary = f"""
        <div class="card total-summary">
            <h2>总览</h2>
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="label">合计净值</div>
                    <div class="value">{_money(total_net)} {base_ccy}</div>
                </div>
                <div class="summary-item">
                    <div class="label">合计浮盈</div>
                    <div class="value" style="color:{pnl_color}">{pnl_sign}{_money(total_pnl)} {base_ccy}</div>
                    <div class="sub" style="color:{pnl_color}">{pnl_sign}{total_pnl_pct:.2f}%</div>
                </div>
            </div>
            <table class="pos-table">
                <thead><tr><th>账户名</th><th>账户号</th><th class="num">净值</th><th class="num">浮动盈亏</th></tr></thead>
                <tbody>{account_rows}</tbody>
            </table>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IBKR 持仓报告 {report_date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0f1117; color: #e0e0e0; padding: 20px; font-size: 14px; }}
  h1 {{ font-size: 20px; color: #fff; margin-bottom: 4px; }}
  .meta {{ color: #888; font-size: 12px; margin-bottom: 20px; }}
  .card {{ background: #1a1d27; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
  .total-summary {{ border: 1px solid #2a3a5c; }}
  h2 {{ font-size: 15px; color: #90caf9; margin-bottom: 14px; letter-spacing: .5px; }}
  h3 {{ font-size: 13px; color: #888; margin: 16px 0 8px; text-transform: uppercase; letter-spacing: .8px; }}
  .summary-grid {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 16px; }}
  .summary-item {{ flex: 1; min-width: 140px; }}
  .label {{ color: #888; font-size: 12px; margin-bottom: 4px; }}
  .value {{ font-size: 22px; font-weight: 600; color: #fff; }}
  .sub {{ font-size: 13px; margin-top: 2px; }}
  .account-header {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .account-id {{ color: #555; font-size: 12px; font-family: monospace; }}
  table.pos-table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  .pos-table th {{ color: #666; font-weight: 500; font-size: 12px; text-align: left;
                   border-bottom: 1px solid #2a2d3a; padding: 6px 8px; }}
  .pos-table td {{ padding: 10px 8px; border-bottom: 1px solid #1e2130; vertical-align: middle; }}
  .pos-table tr:last-child td {{ border-bottom: none; }}
  .pos-table tr:hover td {{ background: #1f2235; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .green {{ color: #26a69a; }}
  .red {{ color: #ef5350; }}
  .gray {{ color: #888; }}
  .pct {{ font-size: 12px; color: #888; margin-left: 4px; }}
  .symbol {{ font-weight: 600; font-size: 15px; color: #fff; }}
  .desc {{ color: #888; font-size: 12px; }}
  .fx-note {{ color: #555; font-size: 11px; }}
  .cash-table td {{ padding: 8px; }}
  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px;
            background: #2a3a5c; color: #90caf9; margin-left: 6px; }}
  footer {{ text-align: center; color: #444; font-size: 11px; margin-top: 24px; }}
</style>
</head>
<body>
<h1>📊 IBKR 持仓报告</h1>
<div class="meta">报告日期：{report_date}　｜　生成时间：{generated_at}</div>

{multi_summary}

{accounts_html}

<footer>由 FinanceBro 自动生成</footer>
</body>
</html>"""


def _render_account(acct: dict) -> str:
    account_id = acct["account_id"]
    alias = acct["alias"] or account_id
    base_ccy = acct["base_currency"]
    s = acct["summary"]
    positions = acct["positions"]
    cash_balances = acct["cash_balances"]

    pnl = s["total_unrealized_pnl_base"]
    pnl_pct = s["total_unrealized_pnl_pct"]
    pnl_color = "#26a69a" if pnl >= 0 else "#ef5350"
    pnl_sign = "+" if pnl >= 0 else ""

    # 持仓行
    pos_rows = ""
    for pos in positions:
        sym = pos["symbol"]
        desc = pos["description"]
        qty = int(pos["quantity"]) if pos["quantity"] == int(pos["quantity"]) else pos["quantity"]
        currency = pos["currency"]
        cost = pos["cost_price"]
        mark = pos["mark_price"]
        mv = pos["market_value"]
        mv_base = pos["market_value_base"]
        p = pos["unrealized_pnl"]
        p_pct = pos["unrealized_pnl_pct"]
        fx = pos["fx_rate"]

        p_cls = "green" if p >= 0 else "red"
        p_sign = "+" if p >= 0 else ""
        dot = "🟢" if p > 0 else ("🔴" if p < 0 else "⚪")

        if currency != base_ccy and fx != 1.0:
            mv_cell = f'{_money(mv)} {currency}<br><span class="fx-note">≈ {_money(mv_base)} {base_ccy}</span>'
            pnl_cell = f'{p_sign}{_money(p)} {currency}'
        else:
            mv_cell = f'{_money(mv)} {base_ccy}'
            pnl_cell = f'{p_sign}{_money(p)} {base_ccy}'

        pos_rows += f"""<tr>
            <td>{dot} <span class="symbol">{sym}</span><br><span class="desc">{desc}</span></td>
            <td class="num">{qty}<br><span class="fx-note">@ {cost:.4f}</span></td>
            <td class="num">{mark}</td>
            <td class="num">{mv_cell}</td>
            <td class="num {p_cls}">{pnl_cell}<br><span class="pct">{p_sign}{p_pct:.2f}%</span></td>
        </tr>"""

    pos_section = f"""
    <h3>持仓明细</h3>
    <table class="pos-table">
        <thead>
            <tr>
                <th>标的</th>
                <th class="num">持仓 / 成本</th>
                <th class="num">现价</th>
                <th class="num">市值</th>
                <th class="num">浮动盈亏</th>
            </tr>
        </thead>
        <tbody>{pos_rows}</tbody>
    </table>""" if positions else "<p class='gray'>暂无持仓</p>"

    # 现金行
    cash_rows = "".join(
        f"""<tr>
            <td>{cb['currency']}</td>
            <td class="num">{_money(cb['ending_cash'])}</td>
            <td class="num gray">≈ {_money(cb['ending_cash_base'])} {base_ccy}</td>
        </tr>"""
        for cb in cash_balances
    )
    cash_section = f"""
    <h3>现金余额</h3>
    <table class="pos-table cash-table">
        <thead><tr><th>币种</th><th class="num">余额</th><th class="num">折合 {base_ccy}</th></tr></thead>
        <tbody>{cash_rows}</tbody>
    </table>""" if cash_balances else ""

    return f"""<div class="card">
    <div class="account-header">
        <h2>{alias} <span class="account-id">{account_id}</span></h2>
    </div>
    <div class="summary-grid">
        <div class="summary-item">
            <div class="label">净值</div>
            <div class="value">{_money(s['net_liquidation'])} {base_ccy}</div>
        </div>
        <div class="summary-item">
            <div class="label">股票市值</div>
            <div class="value">{_money(s['stock_value_base'])} {base_ccy}</div>
        </div>
        <div class="summary-item">
            <div class="label">现金</div>
            <div class="value">{_money(s['cash_base'])} {base_ccy}</div>
        </div>
        <div class="summary-item">
            <div class="label">浮动盈亏</div>
            <div class="value" style="color:{pnl_color}">{pnl_sign}{_money(pnl)} {base_ccy}</div>
            <div class="sub" style="color:{pnl_color}">{pnl_sign}{pnl_pct:.2f}%</div>
        </div>
    </div>
    {pos_section}
    {cash_section}
</div>"""

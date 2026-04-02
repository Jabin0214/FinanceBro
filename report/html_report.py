"""
IBKR 持仓报告 → Telegram HTML / Browser HTML

纯 Python 生成，无需 AI，快速稳定。
"""

from __future__ import annotations

from html import escape

MAX_MSG_LEN = 4000  # Telegram 上限 4096，留余量


def build_report_messages(data: dict) -> list[str]:
    """
    将 parser.parse_flex_xml() 返回的 dict 转为 Telegram HTML 消息列表。
    多个账户各成一段；超过 4000 字符自动分包。
    """
    accounts = data.get("accounts", [])
    generated_at = data.get("generated_at", "")
    report_date = data.get("report_date", "")

    parts: list[str] = []

    if len(accounts) > 1:
        parts.append(_build_total_summary(accounts, report_date))

    for acct in accounts:
        parts.append(_build_account_section(acct))

    if parts:
        footer = f"\n<i>报告时间：{generated_at}</i>"
        if len(parts[-1]) + len(footer) <= MAX_MSG_LEN:
            parts[-1] += footer
        else:
            parts.append(footer)

    result: list[str] = []
    for part in parts:
        result.extend(_split(part))

    return result


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


def _build_account_section(acct: dict) -> str:
    account_id = acct["account_id"]
    alias = acct["alias"] or account_id
    base_ccy = acct["base_currency"]
    s = acct["summary"]
    positions = acct["positions"]
    cash_balances = acct["cash_balances"]

    lines: list[str] = []
    title = f"<b>{alias}</b>" if alias != account_id else f"<b>{account_id}</b>"
    lines += [
        f"{'━' * 20}",
        f"{title}  <code>{account_id}</code>",
        "",
    ]

    lines += [
        "<b>账户概览</b>",
        f"净值　　{_money(s['net_liquidation'])} {base_ccy}",
        f"股票市值  {_money(s['stock_value_base'])} {base_ccy}",
        f"现金　　{_money(s['cash_base'])} {base_ccy}",
        f"浮动盈亏  {_pnl_str(s['total_unrealized_pnl_base'])} {base_ccy}　{_pct(s['total_unrealized_pnl_pct'])}",
        "",
    ]

    if positions:
        lines.append("<b>持仓明细</b>")
        for pos in positions:
            lines.append(_build_position_line(pos, base_ccy))
        lines.append("")
    else:
        lines += ["<i>暂无持仓</i>", ""]

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
    mv = pos["market_value"]
    mv_base = pos["market_value_base"]
    pnl = pos["unrealized_pnl"]
    pnl_pct = pos["unrealized_pnl_pct"]
    fx = pos["fx_rate"]

    indicator = _pnl_indicator(pnl)

    if currency != base_ccy and fx != 1.0:
        mv_str = f"{_money(mv)} {currency}　≈ {_money(mv_base)} {base_ccy}"
        pnl_str = f"{_pnl_str(pnl)} {currency}"
    else:
        mv_str = f"{_money(mv)} {base_ccy}"
        pnl_str = f"{_pnl_str(pnl)} {base_ccy}"

    return (
        f"{indicator} <b>{symbol}</b> <i>{desc}</i>\n"
        f"     市值 {mv_str}\n"
        f"     浮盈 {pnl_str}　{_pct(pnl_pct)}"
    )


def _money(value: float) -> str:
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
    if value < 0:
        return "🔴"
    return "⚪"


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _split(text: str) -> list[str]:
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


def build_html_file(data: dict, output_path: str) -> str:
    html = _render_html(data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def _render_html(data: dict) -> str:
    accounts = data.get("accounts", [])
    generated_at = data.get("generated_at", "")
    report_date = data.get("report_date", "")

    metrics = _portfolio_metrics(accounts)
    base_ccy = metrics["base_currency"]
    risk_items = _build_risk_items(metrics)
    summary_sentence = _build_summary_sentence(metrics)
    account_cards = "".join(_render_account_snapshot(acct) for acct in accounts)
    top_positions = _render_top_positions(metrics["positions"], base_ccy)
    full_holdings = _render_full_holdings(metrics["positions"], base_ccy)
    cash_table = _render_cash_section(metrics["cash_balances"], base_ccy)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IBKR Portfolio Report {escape(report_date)}</title>
<style>
  :root {{
    --bg: #f6f3ee;
    --card: #ffffff;
    --ink: #18212f;
    --muted: #697386;
    --line: #e5ddd0;
    --accent: #183f63;
    --good: #1f7a57;
    --warn: #b7791f;
    --danger: #b1453b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--ink);
    background: var(--bg);
  }}
  .page {{
    max-width: 1180px;
    margin: 0 auto;
    padding: 24px 16px 40px;
  }}
  .hero {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 20px;
    margin-bottom: 16px;
  }}
  .eyebrow {{
    color: var(--accent);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 6px;
  }}
  h1 {{
    margin: 0;
    font-size: clamp(26px, 4vw, 40px);
    line-height: 1.1;
    font-weight: 700;
  }}
  .hero-copy {{
    display: grid;
    grid-template-columns: 1.6fr 1fr;
    gap: 16px;
    margin-top: 14px;
    align-items: start;
  }}
  .hero p {{
    margin: 0;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.6;
  }}
  .hero-meta {{
    background: #faf8f4;
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 12px 14px;
  }}
  .meta-row {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 13px;
    padding: 7px 0;
    border-bottom: 1px solid var(--line);
  }}
  .meta-row:last-child {{ border-bottom: none; }}
  .meta-label {{ color: var(--muted); }}
  .section {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 18px;
    margin-bottom: 16px;
  }}
  .section-title {{
    margin: 0 0 14px;
    font-size: 18px;
  }}
  .grid {{
    display: grid;
    gap: 12px;
  }}
  .metric-grid {{
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }}
  .metric-card {{
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 16px;
    background: #faf8f4;
  }}
  .metric-label {{
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 8px;
  }}
  .metric-value {{
    font-size: clamp(24px, 3vw, 32px);
    line-height: 1.1;
    font-weight: 700;
  }}
  .positive {{ color: var(--good); }}
  .negative {{ color: var(--danger); }}
  .neutral {{ color: var(--ink); }}
  .pill {{
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
  }}
  .pill.good {{ background: #eaf5ef; color: var(--good); }}
  .pill.warn {{ background: #fff4de; color: var(--warn); }}
  .pill.danger {{ background: #fce9e4; color: var(--danger); }}
  .risk-list {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }}
  .risk-card {{
    border-radius: 16px;
    padding: 14px;
    border: 1px solid var(--line);
    background: #faf8f4;
  }}
  .risk-card.good {{ border-color: #d7eadf; }}
  .risk-card.warn {{ border-color: #efd8ad; }}
  .risk-card.danger {{ border-color: #edc3bc; }}
  .risk-title {{
    margin: 10px 0 6px;
    font-size: 15px;
  }}
  .risk-copy {{
    margin: 0;
    line-height: 1.5;
    font-size: 13px;
  }}
  .alloc-grid {{
    grid-template-columns: 1fr;
  }}
  .bars {{
    display: grid;
    gap: 12px;
  }}
  .bar-row {{
    display: grid;
    gap: 6px;
  }}
  .bar-head {{
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 13px;
  }}
  .bar-track {{
    height: 12px;
    background: #ede7dd;
    border-radius: 999px;
    overflow: hidden;
  }}
  .bar-fill {{
    height: 100%;
    border-radius: inherit;
  }}
  .bar-fill.equity {{ background: #224f7a; }}
  .bar-fill.cash {{ background: #b7791f; }}
  .bar-fill.other {{ background: #8a7762; }}
  .account-grid {{
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }}
  .account-card {{
    border: 1px solid var(--line);
    background: #faf8f4;
    border-radius: 16px;
    padding: 14px;
  }}
  .account-name {{
    font-size: 18px;
    margin: 0 0 4px;
  }}
  .account-id {{
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 12px;
  }}
  .mini-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }}
  .mini-item {{
    border-top: 1px solid var(--line);
    padding-top: 8px;
  }}
  .mini-label {{
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 4px;
  }}
  .mini-value {{
    font-size: 16px;
    font-weight: 700;
    line-height: 1.3;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
  }}
  th, td {{
    padding: 10px 8px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
    font-size: 13px;
  }}
  th {{
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}
  td.num, th.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}
  .symbol {{
    font-weight: 700;
    font-size: 14px;
  }}
  .desc {{
    color: var(--muted);
    margin-top: 3px;
    font-size: 12px;
    line-height: 1.4;
  }}
  .subline {{
    color: var(--muted);
    font-size: 11px;
    margin-top: 3px;
  }}
  .table-wrap {{
    overflow-x: auto;
  }}
  footer {{
    color: var(--muted);
    text-align: center;
    padding-top: 4px;
    font-size: 12px;
  }}
  @media (max-width: 960px) {{
    .hero-copy,
    .alloc-grid,
    .risk-list,
    .metric-grid {{
      grid-template-columns: 1fr;
    }}
  }}
  @media (max-width: 720px) {{
    .page {{ padding: 16px 12px 28px; }}
    .hero,
    .section {{ padding: 14px; border-radius: 16px; }}
    .mini-grid {{ grid-template-columns: 1fr; }}
    .metric-value {{ font-size: 26px; }}
  }}
</style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="eyebrow">Consolidated Portfolio</div>
      <h1>IBKR 账户总览</h1>
      <div class="hero-copy">
        <p>{escape(summary_sentence)}</p>
        <div class="hero-meta">
          <div class="meta-row"><span class="meta-label">报告日期</span><strong>{escape(report_date or "-")}</strong></div>
          <div class="meta-row"><span class="meta-label">生成时间</span><strong>{escape(generated_at or "-")}</strong></div>
          <div class="meta-row"><span class="meta-label">账户数量</span><strong>{metrics["account_count"]}</strong></div>
          <div class="meta-row"><span class="meta-label">基准货币</span><strong>{escape(base_ccy)}</strong></div>
        </div>
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">总览</h2>
      <div class="grid metric-grid">
        {_render_metric_card("总资产", _money(metrics["total_net"]), base_ccy)}
        {_render_metric_card("账面盈亏", _pnl_str(metrics["total_pnl"]), base_ccy, _sentiment_class(metrics["total_pnl"]))}
        {_render_metric_card("现金占比", _plain_pct(metrics["cash_ratio"]), "", _level_to_class(metrics["cash_ratio_level"]))}
        {_render_metric_card("最大持仓占比", _plain_pct(metrics["largest_position_weight"]), "", _level_to_class(metrics["largest_position_level"]))}
        {_render_metric_card("前五大集中度", _plain_pct(metrics["top5_concentration"]), "", _level_to_class(metrics["top5_level"]))}
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">风险</h2>
      <div class="risk-list">
        {risk_items}
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">资金分布</h2>
      <div class="grid alloc-grid">
        <div class="bars">
          {_render_bar("股票仓位", metrics["equity_ratio"], "equity", f"{_money(metrics['total_stock'])} {base_ccy}")}
          {_render_bar("现金仓位", metrics["cash_ratio"], "cash", f"{_money(metrics['total_cash'])} {base_ccy}")}
          {_render_bar("其他项目", metrics["other_ratio"], "other", f"{_money(metrics['other_assets'])} {base_ccy}")}
        </div>
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">分账户</h2>
      <div class="grid account-grid">
        {account_cards}
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">前五持仓</h2>
      <div class="table-wrap">
        {top_positions}
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">全部持仓</h2>
      <div class="table-wrap">
        {full_holdings}
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">现金</h2>
      <div class="table-wrap">
        {cash_table}
      </div>
    </section>

    <footer>本页根据 IBKR 报表自动生成。所有盈亏均为账面值，仅供你做账户结构和风险观察。</footer>
  </div>
</body>
</html>"""


def _portfolio_metrics(accounts: list[dict]) -> dict:
    positions: list[dict] = []
    cash_balances: list[dict] = []

    total_net = sum(a["summary"]["net_liquidation"] for a in accounts)
    total_stock = sum(a["summary"]["stock_value_base"] for a in accounts)
    total_cash = sum(a["summary"]["cash_base"] for a in accounts)
    total_pnl = sum(a["summary"]["total_unrealized_pnl_base"] for a in accounts)
    total_cost = sum(a["summary"]["total_cost_base"] for a in accounts)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0
    base_currency = accounts[0]["base_currency"] if accounts else "HKD"

    for acct in accounts:
        alias = acct["alias"] or acct["account_id"]
        net = acct["summary"]["net_liquidation"]
        for pos in acct.get("positions", []):
            position = dict(pos)
            position["account_label"] = alias
            position["account_id"] = acct["account_id"]
            position["base_currency"] = acct["base_currency"]
            position["account_weight"] = (pos["market_value_base"] / net * 100) if net else 0.0
            positions.append(position)

        for cb in acct.get("cash_balances", []):
            balance = dict(cb)
            balance["account_label"] = alias
            balance["account_id"] = acct["account_id"]
            cash_balances.append(balance)

    positions.sort(key=lambda item: item["market_value_base"], reverse=True)
    for position in positions:
        position["weight"] = (position["market_value_base"] / total_net * 100) if total_net else 0.0
    largest_position_weight = (positions[0]["market_value_base"] / total_net * 100) if positions and total_net else 0.0
    top5_concentration = (
        sum(p["market_value_base"] for p in positions[:5]) / total_net * 100
        if total_net else 0.0
    )
    equity_ratio = (total_stock / total_net * 100) if total_net else 0.0
    cash_ratio = (total_cash / total_net * 100) if total_net else 0.0
    other_assets = max(total_net - total_stock - total_cash, 0.0)
    other_ratio = (other_assets / total_net * 100) if total_net else 0.0

    best_position = max(positions, key=lambda item: item["unrealized_pnl_base"], default=None)
    worst_position = min(positions, key=lambda item: item["unrealized_pnl_base"], default=None)

    return {
        "account_count": len(accounts),
        "base_currency": base_currency,
        "positions": positions,
        "cash_balances": cash_balances,
        "total_net": total_net,
        "total_stock": total_stock,
        "total_cash": total_cash,
        "other_assets": other_assets,
        "total_pnl": total_pnl,
        "total_cost": total_cost,
        "total_pnl_pct": total_pnl_pct,
        "position_count": len(positions),
        "equity_ratio": equity_ratio,
        "cash_ratio": cash_ratio,
        "other_ratio": other_ratio,
        "largest_position_weight": largest_position_weight,
        "top5_concentration": top5_concentration,
        "largest_position_level": _risk_level(largest_position_weight, 10, 20),
        "top5_level": _risk_level(top5_concentration, 35, 55),
        "cash_ratio_level": _cash_level(cash_ratio),
        "cash_ratio_note": _cash_note(cash_ratio),
        "largest_position_note": _largest_position_note(largest_position_weight, positions[0] if positions else None),
        "top5_note": _top5_note(top5_concentration, len(positions)),
        "best_position": best_position,
        "worst_position": worst_position,
    }


def _build_summary_sentence(metrics: dict) -> str:
    pnl_phrase = "处于账面盈利状态" if metrics["total_pnl"] >= 0 else "处于账面亏损状态"
    cash_phrase = {
        "good": "现金缓冲相对充足",
        "warn": "现金缓冲中等",
        "danger": "现金缓冲偏薄",
    }[metrics["cash_ratio_level"]]
    concentration_phrase = {
        "good": "持仓分散度相对健康",
        "warn": "持仓有一定集中",
        "danger": "持仓明显集中在少数标的",
    }[metrics["top5_level"]]
    return (
        f"你的账户当前总资产约为 {_money(metrics['total_net'])} {metrics['base_currency']}，"
        f"{pnl_phrase}，当前账面盈亏为 {_pnl_str(metrics['total_pnl'])} {metrics['base_currency']}。"
        f"从结构上看，{cash_phrase}，{concentration_phrase}。"
    )


def _build_risk_items(metrics: dict) -> str:
    items = [
        {
            "level": metrics["top5_level"],
            "title": "持仓集中度",
            "copy": f"前五大持仓占比 {_plain_pct(metrics['top5_concentration'])}",
        },
        {
            "level": metrics["cash_ratio_level"],
            "title": "现金缓冲",
            "copy": f"现金占比 {_plain_pct(metrics['cash_ratio'])}",
        },
        {
            "level": metrics["largest_position_level"],
            "title": "最大单一持仓",
            "copy": f"最大持仓占比 {_plain_pct(metrics['largest_position_weight'])}",
        },
    ]

    return "".join(
        f"""
        <article class="risk-card {item['level']}">
          <div class="pill {item['level']}">{_level_label(item['level'])}</div>
          <h3 class="risk-title">{escape(item['title'])}</h3>
          <p class="risk-copy">{escape(item['copy'])}</p>
        </article>
        """
        for item in items
    )


def _build_allocation_cards(metrics: dict) -> str:
    cards = [
        (
            "股票仓位",
            "股票市值占总资产的比例。这个比例越高，整体波动通常越大，但上涨时收益弹性也更高。",
            f"当前约 {_plain_pct(metrics['equity_ratio'])} 的资产在股票里。",
        ),
        (
            "现金仓位",
            "现金相当于你的缓冲垫。现金不是坏事，它能让你在下跌时更从容，也能减少组合波动。",
            metrics["cash_ratio_note"],
        ),
        (
            "持仓数量",
            "持仓数量本身不代表一定更好，但过少通常意味着风险集中，过多则可能难以跟踪。",
            f"你当前共有 {metrics['position_count']} 个持仓。",
        ),
    ]
    return "".join(
        f"""
        <div class="helper-card">
          <h3>{escape(title)}</h3>
          <p>{escape(body)} {escape(note)}</p>
        </div>
        """
        for title, body, note in cards
    )


def _build_action_items(metrics: dict) -> str:
    items = [
        {
            "title": "先看仓位是不是太重",
            "copy": (
                f"你目前股票仓位约 {_plain_pct(metrics['equity_ratio'])}，"
                " 这代表大部分资产已经暴露在市场波动里。"
            ),
            "next_step": _equity_action_note(metrics["equity_ratio"]),
        },
        {
            "title": "再看你有没有缓冲空间",
            "copy": (
                f"当前现金占比约 {_plain_pct(metrics['cash_ratio'])}。"
                " 现金越少，市场继续下跌时越难从容调整。"
            ),
            "next_step": metrics["cash_ratio_note"],
        },
        {
            "title": "最后看风险是不是压在少数股票上",
            "copy": (
                f"前五大持仓集中度为 {_plain_pct(metrics['top5_concentration'])}，"
                f" 最大单一持仓为 {_plain_pct(metrics['largest_position_weight'])}。"
            ),
            "next_step": _concentration_action_note(
                metrics["top5_concentration"],
                metrics["largest_position_weight"],
            ),
        },
    ]

    return "".join(
        f"""
        <article class="action-card">
          <h3>{escape(item['title'])}</h3>
          <p>{escape(item['copy'])}</p>
          <p><strong>你可以这样理解：</strong> {escape(item['next_step'])}</p>
        </article>
        """
        for item in items
    )


def _render_account_snapshot(acct: dict) -> str:
    alias = acct["alias"] or acct["account_id"]
    account_id = acct["account_id"]
    base_ccy = acct["base_currency"]
    s = acct["summary"]
    positions = acct.get("positions", [])
    cash_ratio = (s["cash_base"] / s["net_liquidation"] * 100) if s["net_liquidation"] else 0.0

    return f"""
    <article class="account-card">
      <h3 class="account-name">{escape(alias)}</h3>
      <div class="account-id">{escape(account_id)} · 基准货币 {escape(base_ccy)}</div>
      <div class="mini-grid">
        <div class="mini-item">
          <div class="mini-label">总资产</div>
          <div class="mini-value">{_money(s['net_liquidation'])} {escape(base_ccy)}</div>
        </div>
        <div class="mini-item">
          <div class="mini-label">账面盈亏</div>
          <div class="mini-value {_sentiment_class(s['total_unrealized_pnl_base'])}">{_pnl_str(s['total_unrealized_pnl_base'])} {escape(base_ccy)}</div>
        </div>
        <div class="mini-item">
          <div class="mini-label">股票市值</div>
          <div class="mini-value">{_money(s['stock_value_base'])} {escape(base_ccy)}</div>
        </div>
        <div class="mini-item">
          <div class="mini-label">现金占比</div>
          <div class="mini-value">{_plain_pct(cash_ratio)}</div>
        </div>
        <div class="mini-item">
          <div class="mini-label">持仓数量</div>
          <div class="mini-value">{len(positions)}</div>
        </div>
        <div class="mini-item">
          <div class="mini-label">收益率</div>
          <div class="mini-value {_sentiment_class(s['total_unrealized_pnl_pct'])}">{_signed_pct(s['total_unrealized_pnl_pct'])}</div>
        </div>
      </div>
    </article>
    """


def _render_movers(metrics: dict, base_ccy: str) -> str:
    winner = metrics["best_position"]
    loser = metrics["worst_position"]

    return (
        _render_mover_card(
            "当前最赚钱的持仓",
            "最好表现",
            winner,
            base_ccy,
            "这只持仓目前是你组合里账面贡献最大的标的。",
        )
        + _render_mover_card(
            "当前拖累最大的持仓",
            "最大拖累",
            loser,
            base_ccy,
            "这只持仓目前对你的整体账面结果拖累最大，值得重点复盘。",
        )
    )


def _render_mover_card(title: str, kicker: str, position: dict | None, base_ccy: str, default_note: str) -> str:
    if not position:
        return f"""
        <article class="spotlight-card">
          <div class="spotlight-kicker">{escape(kicker)}</div>
          <h3 class="spotlight-title">{escape(title)}</h3>
          <div class="spotlight-meta">当前没有可用持仓数据。</div>
          <div class="spotlight-note">等有持仓后，这里会帮你快速找出最赚钱和最拖累的标的。</div>
        </article>
        """

    return f"""
    <article class="spotlight-card">
      <div class="spotlight-kicker">{escape(kicker)}</div>
      <h3 class="spotlight-title">{escape(position['symbol'])}</h3>
      <div class="spotlight-meta">{escape(position['description'])} · {escape(position['account_label'])}</div>
      <div class="spotlight-value {_sentiment_class(position['unrealized_pnl_base'])}">{_pnl_str(position['unrealized_pnl_base'])} {escape(base_ccy)}</div>
      <div class="spotlight-meta">收益率 {_signed_pct(position['unrealized_pnl_pct'])} · 仓位占比 {_plain_pct(position['weight'])}</div>
      <div class="spotlight-note">{escape(default_note)}</div>
    </article>
    """


def _render_top_positions(positions: list[dict], base_ccy: str) -> str:
    rows = []
    for pos in positions[:5]:
        rows.append(
            f"""
            <tr>
              <td>
                <div class="symbol">{escape(pos['symbol'])}</div>
                <div class="desc">{escape(pos['description'])}</div>
                <div class="subline">{escape(pos['account_label'])}</div>
              </td>
              <td class="num">{_money(pos['market_value_base'])} {escape(base_ccy)}</td>
              <td class="num">{_plain_pct(pos['weight'])}</td>
              <td class="num {_sentiment_class(pos['unrealized_pnl_base'])}">{_pnl_str(pos['unrealized_pnl_base'])} {escape(base_ccy)}</td>
              <td class="num {_sentiment_class(pos['unrealized_pnl_pct'])}">{_signed_pct(pos['unrealized_pnl_pct'])}</td>
            </tr>
            """
        )

    if not rows:
        return "<p class='section-subtitle'>当前没有持仓数据。</p>"

    return f"""
    <table>
      <thead>
        <tr>
          <th>持仓</th>
          <th class="num">市值</th>
          <th class="num">占总组合比例</th>
          <th class="num">账面盈亏</th>
          <th class="num">收益率</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def _render_full_holdings(positions: list[dict], base_ccy: str) -> str:
    if not positions:
        return "<p class='section-subtitle'>当前没有持仓数据。</p>"

    headers = [
        ("标的", None, None),
        ("数量", None, None),
        ("成本价", None, None),
        ("现价", None, None),
        ("市值", None, None),
        ("仓位占比", None, None),
        ("账面盈亏", None, None),
        ("收益率", None, None),
    ]

    num_class = ' class="num"'
    header_html = "".join(
        f"<th{num_class if label != '标的' else ''}>{escape(label)}</th>"
        for label, title, body in headers
    )

    rows = []
    for pos in positions:
        quantity = int(pos["quantity"]) if pos["quantity"] == int(pos["quantity"]) else f"{pos['quantity']:.2f}"
        market_value = _money(pos["market_value"])
        if pos["currency"] != base_ccy and pos["fx_rate"] != 1.0:
            value_cell = (
                f"{market_value} {escape(pos['currency'])}"
                f"<div class='subline'>≈ {_money(pos['market_value_base'])} {escape(base_ccy)}</div>"
            )
        else:
            value_cell = f"{market_value} {escape(base_ccy)}"

        rows.append(
            f"""
            <tr>
              <td>
                <div class="symbol">{escape(pos['symbol'])}</div>
                <div class="desc">{escape(pos['description'])}</div>
                <div class="subline">{escape(pos['account_label'])}</div>
              </td>
              <td class="num">{quantity}</td>
              <td class="num">{pos['cost_price']:.4f}</td>
              <td class="num">{pos['mark_price']:.4f}</td>
              <td class="num">{value_cell}</td>
              <td class="num">{_plain_pct(pos['weight'])}</td>
              <td class="num {_sentiment_class(pos['unrealized_pnl_base'])}">{_pnl_str(pos['unrealized_pnl_base'])} {escape(base_ccy)}</td>
              <td class="num {_sentiment_class(pos['unrealized_pnl_pct'])}">{_signed_pct(pos['unrealized_pnl_pct'])}</td>
            </tr>
            """
        )

    return f"""
    <table>
      <thead>
        <tr>{header_html}</tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def _render_cash_section(cash_balances: list[dict], base_ccy: str) -> str:
    if not cash_balances:
        return "<p class='section-subtitle'>当前没有现金数据。</p>"

    rows = "".join(
        f"""
        <tr>
          <td>{escape(item['account_label'])}</td>
          <td>{escape(item['currency'])}</td>
          <td class="num">{_money(item['ending_cash'])}</td>
          <td class="num">{_money(item['ending_cash_base'])} {escape(base_ccy)}</td>
        </tr>
        """
        for item in cash_balances
    )
    return f"""
    <table>
      <thead>
        <tr>
          <th>账户</th>
          <th>币种</th>
          <th class="num">现金余额</th>
          <th class="num">折合 {escape(base_ccy)}</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    """


def _render_metric_card(
    label_cn: str,
    value: str,
    unit: str,
    tone: str = "neutral",
) -> str:
    unit_html = f" {escape(unit)}" if unit else ""
    return f"""
    <article class="metric-card">
      <div class="metric-label">{escape(label_cn)}</div>
      <div class="metric-value {tone}">{escape(value)}{unit_html}</div>
    </article>
    """


def _render_bar(label: str, pct: float, css_class: str, value: str) -> str:
    width = max(0.0, min(pct, 100.0))
    return f"""
    <div class="bar-row">
      <div class="bar-head">
        <strong>{escape(label)}</strong>
        <span>{_plain_pct(pct)} · {escape(value)}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill {escape(css_class)}" style="width:{width:.2f}%"></div>
      </div>
    </div>
    """


def _tooltip(title: str, body: str) -> str:
    return (
        f"<button type='button' class='tooltip-trigger' "
        f"data-tip-title='{escape(title, quote=True)}' "
        f"data-tip-body='{escape(body, quote=True)}' aria-label='查看解释'>?</button>"
    )


def _popover_script() -> str:
    return """
const backdrop = document.getElementById('popover-backdrop');
const title = document.getElementById('popover-title');
const body = document.getElementById('popover-body');
const closeBtn = document.getElementById('popover-close');

function closePopover() {
  backdrop.classList.remove('open');
  backdrop.setAttribute('aria-hidden', 'true');
}

document.querySelectorAll('.tooltip-trigger').forEach((button) => {
  button.addEventListener('click', () => {
    title.textContent = button.dataset.tipTitle || '';
    body.textContent = button.dataset.tipBody || '';
    backdrop.classList.add('open');
    backdrop.setAttribute('aria-hidden', 'false');
  });
});

backdrop.addEventListener('click', (event) => {
  if (event.target === backdrop) {
    closePopover();
  }
});

closeBtn.addEventListener('click', closePopover);

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closePopover();
  }
});
"""


def _risk_level(value: float, low: float, high: float) -> str:
    if value >= high:
        return "danger"
    if value >= low:
        return "warn"
    return "good"


def _cash_level(value: float) -> str:
    if value < 8:
        return "danger"
    if value < 18:
        return "warn"
    return "good"


def _cash_note(cash_ratio: float) -> str:
    if cash_ratio < 8:
        return "现金偏少，说明组合更像满仓状态，遇到大波动时缓冲空间有限。"
    if cash_ratio < 18:
        return "现金处于中等水平，说明你有一定缓冲，但防守能力还不算特别强。"
    return "现金缓冲较充足，说明你保留了一定灵活性与防守空间。"


def _largest_position_note(weight: float, position: dict | None) -> str:
    if not position:
        return "当前没有持仓数据。"
    prefix = f"目前最大仓位是 {position['symbol']}，占总资产 {_plain_pct(weight)}。"
    if weight >= 20:
        return prefix + " 这已经是比较显著的单一暴露，走势会明显影响整体账户。"
    if weight >= 10:
        return prefix + " 这是值得持续关注的权重，单一标的已经开始影响组合稳定性。"
    return prefix + " 目前单一标的依赖度还算温和。"


def _top5_note(concentration: float, position_count: int) -> str:
    if position_count == 0:
        return "当前没有持仓数据。"
    if concentration >= 55:
        return "前五大持仓已经主导了大部分结果，组合波动会比较集中。"
    if concentration >= 35:
        return "前五大持仓已有明显影响，建议重点关注其中的大仓位。"
    return "前五大持仓的集中程度还算健康，整体没有过度依赖少数持仓。"


def _equity_action_note(equity_ratio: float) -> str:
    if equity_ratio >= 85:
        return "你的账户已经非常偏向股票，收益弹性高，但回撤时也会更难受。"
    if equity_ratio >= 65:
        return "你的仓位属于偏进攻型，既能参与上涨，也需要接受更明显波动。"
    return "你的股票仓位不算极端，整体进攻性相对温和。"


def _concentration_action_note(top5_concentration: float, largest_position_weight: float) -> str:
    if top5_concentration >= 55 or largest_position_weight >= 20:
        return "你需要重点盯住前几大仓位，因为它们已经足以决定大部分账户波动。"
    if top5_concentration >= 35 or largest_position_weight >= 10:
        return "组合开始有集中倾向，建议优先理解大仓位背后的逻辑和风险。"
    return "目前集中度还算温和，风险没有明显压在极少数持仓上。"


def _level_label(level: str) -> str:
    return {
        "good": "相对稳健",
        "warn": "需要留意",
        "danger": "重点关注",
    }[level]


def _level_to_class(level: str) -> str:
    return {
        "good": "positive",
        "warn": "neutral",
        "danger": "negative",
    }[level]


def _sentiment_class(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _plain_pct(value: float) -> str:
    return f"{value:.1f}%"

"""IBKR 持仓数据 → 浏览器深色主题 HTML 报表（纯 Python，无 AI）。"""

from __future__ import annotations

from html import escape


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
    top_positions = _render_top_positions(metrics["positions"], base_ccy, metrics["can_consolidate"])
    full_holdings = _render_full_holdings(metrics["positions"], base_ccy, metrics["can_consolidate"])
    cash_table = _render_cash_section(metrics["cash_balances"], base_ccy)
    mixed_currency_notice = _render_mixed_currency_notice(metrics)

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

    {mixed_currency_notice}

    <section class="section">
      <h2 class="section-title">总览</h2>
      <div class="grid metric-grid">
        {_render_metric_card("总资产", _metric_value(metrics["total_net"], base_ccy, metrics["can_consolidate"]), "")}
        {_render_metric_card("账面盈亏", _metric_value(metrics["total_pnl"], base_ccy, metrics["can_consolidate"], pnl=True), "", _sentiment_class(metrics["total_pnl"]) if metrics["can_consolidate"] else "neutral")}
        {_render_metric_card("现金占比", _ratio_value(metrics["cash_ratio"], metrics["can_consolidate"]), "", _level_to_class(metrics["cash_ratio_level"]) if metrics["can_consolidate"] else "neutral")}
        {_render_metric_card("最大持仓占比", _ratio_value(metrics["largest_position_weight"], True), "", _level_to_class(metrics["largest_position_level"]))}
        {_render_metric_card("前五大集中度", _ratio_value(metrics["top5_concentration"], metrics["can_consolidate"]), "", _level_to_class(metrics["top5_level"]) if metrics["can_consolidate"] else "neutral")}
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
          {_render_bar("股票仓位", metrics["equity_ratio"], "equity", f"{_money(metrics['total_stock'])} {base_ccy}" if metrics["can_consolidate"] else "-")}
          {_render_bar("现金仓位", metrics["cash_ratio"], "cash", f"{_money(metrics['total_cash'])} {base_ccy}" if metrics["can_consolidate"] else "-")}
          {_render_bar("其他项目", metrics["other_ratio"], "other", f"{_money(metrics['other_assets'])} {base_ccy}" if metrics["can_consolidate"] else "-")}
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
    base_currencies = sorted({a["base_currency"] for a in accounts})
    can_consolidate = len(base_currencies) <= 1

    total_net = sum(a["summary"]["net_liquidation"] for a in accounts) if can_consolidate else 0.0
    total_stock = sum(a["summary"]["stock_value_base"] for a in accounts) if can_consolidate else 0.0
    total_cash = sum(a["summary"]["cash_base"] for a in accounts) if can_consolidate else 0.0
    total_pnl = sum(a["summary"]["total_unrealized_pnl_base"] for a in accounts) if can_consolidate else 0.0
    total_cost = sum(a["summary"]["total_cost_base"] for a in accounts) if can_consolidate else 0.0
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0
    base_currency = base_currencies[0] if base_currencies else "HKD"

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

    if can_consolidate:
        positions.sort(key=lambda item: item["market_value_base"], reverse=True)
    else:
        positions.sort(key=lambda item: (item["account_label"], -abs(item["market_value_base"]), item["symbol"]))
    for position in positions:
        position["weight"] = (
            (position["market_value_base"] / total_net * 100)
            if can_consolidate and total_net
            else position["account_weight"]
        )
    largest_position_weight = (
        (positions[0]["market_value_base"] / total_net * 100)
        if can_consolidate and positions and total_net
        else max((p["account_weight"] for p in positions), default=0.0)
    )
    top5_concentration = (
        sum(p["market_value_base"] for p in positions[:5]) / total_net * 100
        if can_consolidate and total_net else 0.0
    )
    equity_ratio = (total_stock / total_net * 100) if can_consolidate and total_net else 0.0
    cash_ratio = (total_cash / total_net * 100) if can_consolidate and total_net else 0.0
    other_assets = max(total_net - total_stock - total_cash, 0.0) if can_consolidate else 0.0
    other_ratio = (other_assets / total_net * 100) if can_consolidate and total_net else 0.0

    return {
        "account_count": len(accounts),
        "can_consolidate": can_consolidate,
        "base_currency": base_currency,
        "base_currencies": base_currencies,
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
    }


def _build_summary_sentence(metrics: dict) -> str:
    if not metrics["can_consolidate"]:
        currencies = " / ".join(metrics["base_currencies"])
        return f"检测到多个基准货币账户（{currencies}），本页不做错误合并；总览请以分账户数据为准。"

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
    if not metrics["can_consolidate"]:
        return """
        <article class="risk-card warn">
          <div class="pill warn">分账户查看</div>
          <h3 class="risk-title">检测到多基准货币账户</h3>
          <p class="risk-copy">已停用合并后的风险比例，避免把不同货币直接相加。</p>
        </article>
        """

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


def _render_mixed_currency_notice(metrics: dict) -> str:
    if metrics["can_consolidate"]:
        return ""
    currencies = " / ".join(metrics["base_currencies"])
    return f"""
    <section class="section">
      <h2 class="section-title">说明</h2>
      <div class="risk-card warn">
        <div class="pill warn">多基准货币</div>
        <h3 class="risk-title">已关闭错误合并</h3>
        <p class="risk-copy">检测到多个基准货币账户（{escape(currencies)}）。本页不再把不同货币直接相加，合并比例仅在同一基准货币下显示。</p>
      </div>
    </section>
    """


def _metric_value(value: float, unit: str, can_consolidate: bool, pnl: bool = False) -> str:
    if not can_consolidate:
        return "-"
    return f"{_pnl_str(value) if pnl else _money(value)} {unit}".strip()


def _ratio_value(value: float, enabled: bool) -> str:
    return _plain_pct(value) if enabled else "-"


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
def _render_top_positions(positions: list[dict], base_ccy: str, can_consolidate: bool) -> str:
    if not can_consolidate:
        return "<p>多基准货币账户未做跨账户持仓排名。</p>"

    rows = []
    for pos in positions[:5]:
        row_ccy = base_ccy if can_consolidate else pos["base_currency"]
        rows.append(
            f"""
            <tr>
              <td>
                <div class="symbol">{escape(pos['symbol'])}</div>
                <div class="desc">{escape(pos['description'])}</div>
                <div class="subline">{escape(pos['account_label'])}</div>
              </td>
              <td class="num">{_money(pos['market_value_base'])} {escape(row_ccy)}</td>
              <td class="num">{_plain_pct(pos['weight'])}</td>
              <td class="num {_sentiment_class(pos['unrealized_pnl_base'])}">{_pnl_str(pos['unrealized_pnl_base'])} {escape(row_ccy)}</td>
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
          <th class="num">{'占总组合比例' if can_consolidate else '占账户比例'}</th>
          <th class="num">{'账面盈亏' if can_consolidate else '持仓盈亏'}</th>
          <th class="num">收益率</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """


def _render_full_holdings(positions: list[dict], base_ccy: str, can_consolidate: bool) -> str:
    if not positions:
        return "<p class='section-subtitle'>当前没有持仓数据。</p>"

    headers = [
        ("标的", None, None),
        ("数量", None, None),
        ("成本价", None, None),
        ("现价", None, None),
        ("市值", None, None),
        ("占比", None, None),
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
        row_ccy = base_ccy if can_consolidate else pos["base_currency"]
        quantity = int(pos["quantity"]) if pos["quantity"] == int(pos["quantity"]) else f"{pos['quantity']:.2f}"
        market_value = _money(pos["market_value"])
        if pos["currency"] != row_ccy and pos["fx_rate"] != 1.0:
            value_cell = (
                f"{market_value} {escape(pos['currency'])}"
                f"<div class='subline'>≈ {_money(pos['market_value_base'])} {escape(row_ccy)}</div>"
            )
        else:
            value_cell = f"{market_value} {escape(row_ccy)}"

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
              <td class="num {_sentiment_class(pos['unrealized_pnl_base'])}">{_pnl_str(pos['unrealized_pnl_base'])} {escape(row_ccy)}</td>
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


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _pnl_str(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f}"


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _plain_pct(value: float) -> str:
    return f"{value:.1f}%"

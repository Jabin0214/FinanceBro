"""
Telegram 文本格式化工具。

当前包含：
  - 期权链摘要格式化
  - 卖 Put / Covered Call 候选格式化
"""

from html import escape


def format_option_chain_summary(result: dict, limit: int = 8) -> str:
    if result.get("error"):
        return f"❌ <b>期权链获取失败</b>\n<code>{escape(result['error'])}</code>"

    symbol = escape(result.get("symbol", ""))
    underlying = _fmt_money(result.get("underlying_price"))
    data_type = _fmt_data_type(result.get("data_type"))
    greeks_note = result.get("greeks_note")
    contracts = result.get("contracts", [])
    expirations = result.get("expirations", [])

    lines = [
        f"📈 <b>{symbol} 期权链</b>",
        f"标的价格：<code>{underlying}</code>",
        f"数据类型：<code>{data_type}</code>",
        f"到期日数量：<code>{len(expirations)}</code>",
        f"合约数量：<code>{result.get('total_contracts', len(contracts))}</code>",
    ]

    if greeks_note:
        lines.append(f"提示：<i>{escape(greeks_note)}</i>")

    if contracts:
        lines.append("")
        lines.append("<b>样例合约</b>")
        for contract in contracts[:limit]:
            lines.append(_format_contract_line(contract))

    assumptions = result.get("assumptions") or {}
    if assumptions:
        rights = ", ".join(assumptions.get("rights", [])) or "-"
        lines.extend([
            "",
            "<b>关键假设</b>",
            f"DTE：<code>{escape(str(assumptions.get('dte_range', '-')))}</code>",
            f"方向：<code>{escape(rights)}</code>",
            f"ATM 附近行权价数：<code>{escape(str(assumptions.get('strikes_around_atm', '-')))}</code>",
        ])

    lines.extend([
        "",
        "<i>仅只读展示，不触发下单。</i>",
    ])
    return "\n".join(lines)


def format_option_candidates(result: dict, limit: int = 6) -> str:
    if result.get("error"):
        title = "策略扫描失败"
        return f"❌ <b>{title}</b>\n<code>{escape(result['error'])}</code>"

    symbol = escape(result.get("symbol", ""))
    strategy = escape(result.get("strategy", ""))
    underlying = _fmt_money(result.get("underlying_price"))
    data_type = _fmt_data_type(result.get("data_type"))
    candidates = result.get("candidates", [])

    lines = [
        f"🧭 <b>{symbol} {strategy}</b>",
        f"标的价格：<code>{underlying}</code>",
        f"数据类型：<code>{data_type}</code>",
        f"候选数量：<code>{result.get('total_found', len(candidates))}</code>",
    ]

    greeks_note = result.get("greeks_note")
    if greeks_note:
        lines.append(f"提示：<i>{escape(greeks_note)}</i>")

    assumptions = result.get("assumptions") or {}
    if assumptions:
        lines.extend([
            "",
            "<b>关键假设</b>",
            f"DTE：<code>{escape(str(assumptions.get('dte_range', '-')))}</code>",
            f"Delta：<code>{escape(str(assumptions.get('delta_range', '-')))}</code>",
            f"OI 下限：<code>{escape(str(assumptions.get('min_oi', '-')))}</code>",
            f"Volume 下限：<code>{escape(str(assumptions.get('min_volume', '-')))}</code>",
            f"单标的上限：<code>{escape(str(assumptions.get('max_single_stock_weight_pct', '-')))}%</code>",
            f"同到期日最多候选：<code>{escape(str(assumptions.get('max_candidates_per_expiry', '-')))}</code>",
        ])

    account_context = result.get("account_context") or {}
    if account_context:
        lines.extend([
            "",
            "<b>账户约束</b>",
        ])
        if account_context.get("portfolio_available"):
            lines.append(f"USD 现金：<code>{_fmt_money(account_context.get('usd_cash'))}</code>")
            lines.append(f"持股数量：<code>{account_context.get('shares_held', 0)}</code>")
            lines.append(f"最多可卖 covered call：<code>{account_context.get('max_covered_calls', 0)}</code>")
            lines.append(f"当前标的占净值：<code>{_fmt_percent(account_context.get('symbol_weight_pct'))}</code>")
        else:
            lines.append(f"<code>{escape(str(account_context.get('error', '账户快照不可用')))}</code>")

    if candidates:
        lines.extend(["", "<b>Top 候选</b>"])
        for idx, contract in enumerate(candidates[:limit], start=1):
            lines.append(f"{idx}. {_format_contract_line(contract, include_yield=True)}")
    else:
        lines.extend([
            "",
            "没有找到符合当前条件的候选合约。",
        ])

    risk_note = result.get("risk_note")
    if risk_note:
        lines.extend(["", f"<i>{escape(risk_note)}</i>"])

    return "\n".join(lines)


def _format_contract_line(contract: dict, include_yield: bool = False) -> str:
    expiry = escape(str(contract.get("expiry", "-")))
    right = escape(str(contract.get("right", "-")))
    strike = _fmt_money(contract.get("strike"))
    bid = _fmt_money(contract.get("bid"))
    ask = _fmt_money(contract.get("ask"))
    mid = _fmt_money(contract.get("mid"))
    delta = _fmt_decimal(contract.get("delta"), digits=3)
    iv_pct = _fmt_percent(contract.get("iv_pct"))
    dte = contract.get("dte")

    parts = [
        f"<code>{expiry}</code>",
        right,
        f"K <code>{strike}</code>",
        f"bid/ask <code>{bid}/{ask}</code>",
        f"mid <code>{mid}</code>",
        f"delta <code>{delta}</code>",
        f"IV <code>{iv_pct}</code>",
        f"DTE <code>{dte if dte is not None else '-'}</code>",
    ]

    if include_yield:
        annual_yield = _fmt_percent(contract.get("annual_yield_pct"))
        parts.append(f"年化 <code>{annual_yield}</code>")

    if contract.get("cash_required_usd") is not None:
        parts.append(f"占用 <code>{_fmt_money(contract.get('cash_required_usd'))}</code>")
    if contract.get("max_contracts_by_cash") is not None:
        parts.append(f"现金可卖 <code>{contract.get('max_contracts_by_cash')}</code>")
    if contract.get("max_contracts_by_shares") is not None:
        parts.append(f"持仓可卖 <code>{contract.get('max_contracts_by_shares')}</code>")
    if contract.get("projected_weight_pct") is not None:
        parts.append(f"卖后占比 <code>{_fmt_percent(contract.get('projected_weight_pct'))}</code>")
    if contract.get("current_symbol_weight_pct") is not None:
        parts.append(f"当前占比 <code>{_fmt_percent(contract.get('current_symbol_weight_pct'))}</code>")

    oi = contract.get("oi")
    vol = contract.get("volume")
    parts.append(f"OI/Vol <code>{oi if oi is not None else '-'}/{vol if vol is not None else '-'}</code>")
    return " | ".join(parts)


def _fmt_money(value) -> str:
    if value is None:
        return "-"
    return f"${value:,.2f}"


def _fmt_percent(value) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def _fmt_decimal(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _fmt_data_type(data_type: str | None) -> str:
    mapping = {
        "live": "live",
        "delayed": "delayed",
        "unknown": "unknown",
    }
    return mapping.get(data_type or "", "unknown")

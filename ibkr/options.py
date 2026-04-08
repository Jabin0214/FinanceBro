"""
IBKR 期权链查询与候选筛选 — Phase 4

公开函数：
  get_option_chain(symbol, dte_min, dte_max, rights, max_strikes)
      → 返回原始期权链数据（Iteration 1）

  scan_short_put_candidates(symbol, ...)
      → 筛选 cash-secured put 候选（Iteration 2）

  scan_covered_call_candidates(symbol, ...)
      → 筛选 covered call 候选（Iteration 2）

关键约束（Phase 4 全程）：
  - 只读，不触发任何下单操作
  - 缺失 Greeks 时仍返回基础报价，标注 greeks_available=False
  - TWS 未连接时返回友好错误字典，不抛出异常到上层

初始筛选原则（可后续参数化）：
  cash-secured put  : 优先 20-45 DTE，|delta| 0.15-0.30，OI/volume 满足流动性
  covered call      : 优先 15-45 DTE，delta 0.10-0.25，OI/volume 满足流动性
"""

import asyncio
import logging
import math
from datetime import date, datetime, timedelta
from typing import Optional

from ibkr.models import OptionContract
from ibkr.tws_client import get_tws_client, TWSNotConnectedError

logger = logging.getLogger(__name__)

# 每批最多订阅的合约数，避免触及 IBKR 行情订阅限制
_BATCH_SIZE = 25
# 等待行情数据填充的秒数（延迟数据下适当加长）
_MARKET_DATA_WAIT = 6


# ── 公开函数 ──────────────────────────────────────────────────────────────────

def get_option_chain(
    symbol: str,
    dte_min: int = 0,
    dte_max: int = 60,
    rights: Optional[list] = None,   # ["P"], ["C"], 或 None（两者）
    max_strikes: int = 15,           # ATM 附近各取 max_strikes/2 个行权价
) -> dict:
    """
    获取指定标的的期权链数据（Iteration 1）。

    返回格式：
    {
      "symbol": "AAPL",
      "underlying_price": 175.5,
      "data_type": "live" | "delayed" | "unknown",
      "data_note": "实时行情" | "延迟行情，仅供参考" | "行情状态未知",
      "greeks_available": true,
      "greeks_note": null,
      "expirations": ["20251017", ...],
      "contracts": [...],
      "total_contracts": 30,
      "assumptions": {...},   # 关键假设，便于 Telegram 端展示
      "error": null,
    }
    """
    try:
        client = get_tws_client()
        return client.run(
            _fetch_chain(client.ib, symbol, dte_min, dte_max, rights, max_strikes),
            timeout=120,
        )
    except TWSNotConnectedError as e:
        return _err(symbol, str(e))
    except Exception as e:
        logger.exception("get_option_chain(%s) 异常", symbol)
        return _err(symbol, f"期权链获取失败：{e}")


def scan_short_put_candidates(
    symbol: str,
    dte_min: int = 20,
    dte_max: int = 45,
    delta_min: float = 0.15,
    delta_max: float = 0.30,
    min_oi: int = 100,
    min_volume: int = 10,
    min_premium: float = 0.10,
) -> dict:
    """
    筛选适合卖出的 cash-secured put 候选合约（Iteration 2）。

    筛选逻辑：
      - 只看 Put
      - |delta| 在 [delta_min, delta_max] 范围内
      - OI >= min_oi（无数据时放行但标注）
      - volume >= min_volume（无数据时放行但标注）
      - mid >= min_premium
    按年化收益率倒序排列，返回前 10 条。

    ⚠️ 关键假设会在返回结果中明确标注。
    """
    chain = get_option_chain(
        symbol, dte_min=dte_min, dte_max=dte_max, rights=["P"], max_strikes=20
    )
    if chain.get("error"):
        return chain

    candidates = _filter_contracts(
        contracts=chain["contracts"],
        right_filter="Put",
        delta_min=delta_min,
        delta_max=delta_max,
        use_abs_delta=True,   # Put 的 delta 为负，取绝对值
        min_oi=min_oi,
        min_volume=min_volume,
        min_premium=min_premium,
    )

    return {
        "symbol": symbol,
        "strategy": "cash-secured put",
        "underlying_price": chain.get("underlying_price"),
        "data_type": chain.get("data_type"),
        "data_note": chain.get("data_note"),
        "greeks_available": chain.get("greeks_available"),
        "greeks_note": chain.get("greeks_note"),
        "assumptions": {
            "dte_range": f"{dte_min}–{dte_max} 天",
            "delta_range": f"|delta| {delta_min}–{delta_max}",
            "min_oi": min_oi,
            "min_volume": min_volume,
            "min_premium_per_contract": f"${min_premium:.2f}",
            "note": "资金占用 = 行权价 × 100（每张合约），请确认账户现金充足",
        },
        "candidates": candidates[:10],
        "total_found": len(candidates),
        "risk_note": "⚠️ 非投资建议，仅供决策辅助。卖出 Put 义务为以行权价买入 100 股，请自行评估最大亏损。",
    }


def scan_covered_call_candidates(
    symbol: str,
    dte_min: int = 15,
    dte_max: int = 45,
    delta_min: float = 0.10,
    delta_max: float = 0.25,
    min_oi: int = 100,
    min_volume: int = 10,
    min_premium: float = 0.10,
) -> dict:
    """
    筛选适合卖出的 covered call 候选合约（Iteration 2）。

    筛选逻辑：
      - 只看 Call
      - delta 在 [delta_min, delta_max] 范围内
      - OI >= min_oi
      - volume >= min_volume
      - mid >= min_premium
    按年化收益率倒序排列，返回前 10 条。

    ⚠️ 裸 call 默认不在此工具范围内；调用方应确认持有对应正股。
    """
    chain = get_option_chain(
        symbol, dte_min=dte_min, dte_max=dte_max, rights=["C"], max_strikes=20
    )
    if chain.get("error"):
        return chain

    candidates = _filter_contracts(
        contracts=chain["contracts"],
        right_filter="Call",
        delta_min=delta_min,
        delta_max=delta_max,
        use_abs_delta=False,
        min_oi=min_oi,
        min_volume=min_volume,
        min_premium=min_premium,
    )

    return {
        "symbol": symbol,
        "strategy": "covered call",
        "underlying_price": chain.get("underlying_price"),
        "data_type": chain.get("data_type"),
        "data_note": chain.get("data_note"),
        "greeks_available": chain.get("greeks_available"),
        "greeks_note": chain.get("greeks_note"),
        "assumptions": {
            "dte_range": f"{dte_min}–{dte_max} 天",
            "delta_range": f"delta {delta_min}–{delta_max}",
            "min_oi": min_oi,
            "min_volume": min_volume,
            "min_premium_per_contract": f"${min_premium:.2f}",
            "note": "需已持有标的正股（每张合约对应 100 股），否则视为裸 Call（无限风险）",
        },
        "candidates": candidates[:10],
        "total_found": len(candidates),
        "risk_note": "⚠️ 非投资建议，仅供决策辅助。卖出 Covered Call 可能限制上涨收益，并须确认持仓数量。",
    }


# ── 内部实现 ──────────────────────────────────────────────────────────────────

async def _fetch_chain(ib, symbol: str, dte_min: int, dte_max: int,
                       rights: Optional[list], max_strikes: int) -> dict:
    from ib_insync import Stock, Option

    today = date.today()
    date_min = today + timedelta(days=dte_min)
    date_max = today + timedelta(days=dte_max)
    rights = rights or ["P", "C"]

    # 1. 验证正股合约，取 conId
    stock = Stock(symbol, "SMART", "USD")
    qualified = await ib.qualifyContractsAsync(stock)
    if not qualified:
        return _err(symbol, f"找不到合约：{symbol}，请确认股票代码")
    stock = qualified[0]

    # 2. 获取正股现价
    underlying_price, data_type = await _get_underlying_price(ib, stock)

    # 3. 获取期权链参数（到期日 + 行权价列表）
    try:
        chains = await ib.reqSecDefOptParamsAsync(
            stock.symbol, "", stock.secType, stock.conId
        )
    except Exception as e:
        return _err(symbol, f"期权链参数获取失败：{e}")

    if not chains:
        return _err(symbol, f"无可用期权链：{symbol}（可能不是美股期权标的）")

    # 优先 SMART，否则取第一个有效 exchange
    chain = next((c for c in chains if c.exchange == "SMART"), None)
    if not chain:
        chain = next(
            (c for c in chains if c.expirations and c.strikes), chains[0]
        )

    # 4. 按 DTE 过滤到期日
    expirations = []
    for exp in sorted(chain.expirations):
        try:
            exp_date = datetime.strptime(exp, "%Y%m%d").date()
        except ValueError:
            continue
        if date_min <= exp_date <= date_max:
            dte = (exp_date - today).days
            expirations.append((exp, dte))

    if not expirations:
        available = sorted(chain.expirations)[:8]
        return _err(
            symbol,
            f"在 {dte_min}–{dte_max} DTE 范围内没有可用到期日。"
            f"最近可用到期日：{', '.join(available)}",
        )

    # 5. 过滤 ATM 附近行权价
    all_strikes = sorted(chain.strikes)
    if underlying_price and max_strikes and len(all_strikes) > max_strikes:
        atm_idx = min(range(len(all_strikes)),
                      key=lambda i: abs(all_strikes[i] - underlying_price))
        half = max_strikes // 2
        filtered_strikes = all_strikes[max(0, atm_idx - half): atm_idx + half + 1]
    else:
        filtered_strikes = all_strikes

    # 6. 构造期权合约对象
    opt_contracts = [
        Option(symbol, exp, strike, right, chain.exchange)
        for exp, _ in expirations
        for strike in filtered_strikes
        for right in rights
    ]

    if not opt_contracts:
        return _err(symbol, "没有符合条件的期权合约")

    # 7. 分批 qualify（最多 50/批）
    qualified_opts = []
    for i in range(0, len(opt_contracts), 50):
        batch = opt_contracts[i: i + 50]
        try:
            q = await ib.qualifyContractsAsync(*batch)
            qualified_opts.extend(q)
        except Exception as e:
            logger.warning("qualify 失败（batch %d）: %s", i, e)

    if not qualified_opts:
        return _err(symbol, "合约验证失败，请检查 IB Gateway 连接与行情订阅")

    # 8. 分批请求行情数据
    result_contracts, greeks_available = await _fetch_market_data(
        ib, qualified_opts, underlying_price, today
    )

    return {
        "symbol": symbol,
        "underlying_price": underlying_price,
        "data_type": data_type,
        "data_note": _market_data_note(data_type),
        "greeks_available": greeks_available,
        "greeks_note": (
            None if greeks_available
            else "Greeks 暂不可用（可能需要期权实时行情订阅），已返回基础报价"
        ),
        "expirations": [exp for exp, _ in expirations],
        "contracts": result_contracts,
        "total_contracts": len(result_contracts),
        "assumptions": {
            "dte_range": f"{dte_min}–{dte_max} 天",
            "strikes_around_atm": max_strikes,
            "rights": [("Put" if r == "P" else "Call") for r in rights],
            "exchange": chain.exchange,
        },
        "error": None,
    }


async def _get_underlying_price(ib, stock) -> tuple[Optional[float], str]:
    """获取正股现价，返回 (price, data_type)。"""
    try:
        tickers = await ib.reqTickersAsync(stock)
        if tickers:
            t = tickers[0]
            price = t.marketPrice()
            if price and _valid(price):
                data_type = "delayed" if getattr(t, "marketDataType", 1) in (3, 4) else "live"
                return round(price, 2), data_type
            # fallback to last or close
            for attr in ("last", "close"):
                v = getattr(t, attr, None)
                if v and _valid(v):
                    return round(v, 2), "delayed"
    except Exception as e:
        logger.warning("获取正股价格失败：%s", e)
    return None, "unknown"


async def _fetch_market_data(ib, contracts, underlying_price, today) -> tuple[list, bool]:
    """分批订阅行情，等待数据填充后取消，返回 (合约列表, greeks_available)。"""
    result = []
    greeks_available = False

    for i in range(0, len(contracts), _BATCH_SIZE):
        batch = contracts[i: i + _BATCH_SIZE]
        tickers = []
        try:
            # 订阅行情（generic ticks: 100=option vol, 101=OI, 106=IV）
            for c in batch:
                t = ib.reqMktData(c, genericTickList="100,101,106", snapshot=False,
                                  regulatorySnapshot=False)
                tickers.append(t)

            # 等待数据填充
            await asyncio.sleep(_MARKET_DATA_WAIT)

            # 读取数据
            for ticker in tickers:
                c = ticker.contract
                if not c:
                    continue
                opt = _ticker_to_contract(ticker, c, underlying_price, today)
                if opt:
                    if opt.delta is not None:
                        greeks_available = True
                    result.append(opt.to_dict())

        except Exception as e:
            logger.warning("行情批次 %d 失败：%s", i, e)
        finally:
            for c in batch:
                try:
                    ib.cancelMktData(c)
                except Exception:
                    pass

    return result, greeks_available


def _ticker_to_contract(ticker, contract, underlying_price, today) -> Optional[OptionContract]:
    """将 ib_insync Ticker 转为 OptionContract。"""
    try:
        expiry = contract.lastTradeDateOrContractMonth
        dte = (datetime.strptime(expiry, "%Y%m%d").date() - today).days

        # 提取 Greeks（优先 modelGreeks，其次 bidGreeks/askGreeks）
        greeks = ticker.modelGreeks or ticker.bidGreeks or ticker.askGreeks
        delta = _safe_greek(greeks, "delta") if greeks else None
        gamma = _safe_greek(greeks, "gamma") if greeks else None
        theta = _safe_greek(greeks, "theta") if greeks else None
        vega  = _safe_greek(greeks, "vega")  if greeks else None
        iv    = _safe_greek(greeks, "impliedVol") if greeks else None

        return OptionContract(
            symbol=contract.symbol,
            expiry=expiry,
            strike=contract.strike,
            right=contract.right,
            bid=_safe_price(ticker.bid),
            ask=_safe_price(ticker.ask),
            last=_safe_price(ticker.last),
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            iv=iv,
            oi=_safe_int(ticker.openInterest),
            volume=_safe_int(ticker.volume),
            underlying_price=underlying_price,
            dte=dte,
        )
    except Exception as e:
        logger.debug("转换 ticker 失败：%s", e)
        return None


def _filter_contracts(
    contracts: list,
    right_filter: str,
    delta_min: float,
    delta_max: float,
    use_abs_delta: bool,
    min_oi: int,
    min_volume: int,
    min_premium: float,
) -> list:
    """通用合约筛选逻辑，按年化收益率倒序排列。"""
    candidates = []
    for c in contracts:
        if c.get("right") != right_filter:
            continue

        mid = c.get("mid") or 0
        if mid < min_premium:
            continue

        # Delta 过滤（无 delta 时放行，但不计入排序收益）
        delta = c.get("delta")
        if delta is not None:
            d = abs(delta) if use_abs_delta else delta
            if not (delta_min <= d <= delta_max):
                continue

        # OI 过滤（无数据时放行）
        oi = c.get("oi")
        if oi is not None and min_oi and oi < min_oi:
            continue

        # Volume 过滤（无数据时放行）
        vol = c.get("volume")
        if vol is not None and min_volume and vol < min_volume:
            continue

        candidates.append(c)

    candidates.sort(key=lambda x: x.get("annual_yield_pct") or 0, reverse=True)
    return candidates


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _err(symbol: str, msg: str) -> dict:
    return {"symbol": symbol, "error": msg, "contracts": [], "candidates": []}


def _valid(v) -> bool:
    """检查数值是否有效（非 nan/inf/负）。"""
    try:
        return v is not None and not math.isnan(v) and not math.isinf(v) and v > 0
    except (TypeError, ValueError):
        return False


def _market_data_note(data_type: str) -> str:
    if data_type == "live":
        return "实时行情"
    if data_type == "delayed":
        return "延迟行情，仅供参考"
    return "行情状态未知"


def _safe_price(v) -> Optional[float]:
    return round(v, 4) if _valid(v) else None


def _safe_int(v) -> Optional[int]:
    try:
        iv = int(v)
        return iv if iv >= 0 else None
    except (TypeError, ValueError):
        return None


def _safe_greek(greeks_obj, attr: str) -> Optional[float]:
    v = getattr(greeks_obj, attr, None)
    if v is None:
        return None
    try:
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None

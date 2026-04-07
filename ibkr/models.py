"""
IBKR 数据模型 — Phase 4

OptionContract: 单个期权合约的市场数据快照
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class OptionContract:
    symbol: str
    expiry: str           # "YYYYMMDD"
    strike: float
    right: str            # "P" (put) 或 "C" (call)
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None      # 隐含波动率，小数形式（0.25 = 25%）
    oi: Optional[int] = None        # 未平仓量
    volume: Optional[int] = None    # 当日成交量
    underlying_price: Optional[float] = None
    dte: Optional[int] = None       # 距到期天数

    @property
    def mid(self) -> Optional[float]:
        """买卖中间价。"""
        if self.bid and self.ask and self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 4)
        return None

    @property
    def annual_yield_pct(self) -> Optional[float]:
        """年化收益率 = mid / strike × (365 / dte) × 100，仅供参考。"""
        mid = self.mid
        if mid and self.strike and self.dte and self.dte > 0:
            return round(mid / self.strike * 365 / self.dte * 100, 2)
        return None

    def to_dict(self) -> dict:
        def _fmt(v, digits=4):
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                return None
            return round(v, digits) if isinstance(v, float) else v

        return {
            "symbol": self.symbol,
            "expiry": self.expiry,
            "strike": self.strike,
            "right": "Put" if self.right == "P" else "Call",
            "bid": _fmt(self.bid, 2),
            "ask": _fmt(self.ask, 2),
            "mid": _fmt(self.mid, 2),
            "delta": _fmt(self.delta, 4),
            "gamma": _fmt(self.gamma, 6),
            "theta": _fmt(self.theta, 4),
            "vega": _fmt(self.vega, 4),
            "iv_pct": _fmt(self.iv * 100, 1) if self.iv else None,   # 转换为百分比
            "oi": self.oi,
            "volume": self.volume,
            "underlying_price": _fmt(self.underlying_price, 2),
            "dte": self.dte,
            "annual_yield_pct": self.annual_yield_pct,
        }

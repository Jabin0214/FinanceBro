import unittest
from unittest.mock import patch

from bot.telegram_bot import _parse_option_args
from ibkr.options import (
    get_option_chain,
    scan_covered_call_candidates,
    scan_short_put_candidates,
)
from report.formatter import format_option_candidates, format_option_chain_summary


class OptionInterfaceTests(unittest.TestCase):
    def test_parse_option_args_uses_defaults(self):
        symbol, dte_min, dte_max = _parse_option_args(
            ["AAPL"],
            default_dte_min=20,
            default_dte_max=45,
        )
        self.assertEqual((symbol, dte_min, dte_max), ("AAPL", 20, 45))

    def test_parse_option_args_rejects_extra_args(self):
        with self.assertRaises(ValueError):
            _parse_option_args(
                ["AAPL", "20", "45", "oops"],
                default_dte_min=20,
                default_dte_max=45,
            )

    def test_get_option_chain_validates_dte_range(self):
        result = get_option_chain("AAPL", dte_min=30, dte_max=10)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "dte_min 不能大于 dte_max")

    def test_short_put_scan_validates_delta(self):
        result = scan_short_put_candidates("AAPL", delta_min=0.4, delta_max=0.2)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "delta_min 不能大于 delta_max")

    def test_covered_call_scan_validates_negative_premium(self):
        result = scan_covered_call_candidates("AAPL", min_premium=-1)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "min_premium 不能为负数")

    def test_chain_formatter_handles_error(self):
        rendered = format_option_chain_summary({"error": "boom"})
        self.assertIn("期权链获取失败", rendered)
        self.assertIn("boom", rendered)

    def test_candidate_formatter_renders_candidates(self):
        rendered = format_option_candidates(
            {
                "symbol": "AAPL",
                "strategy": "cash-secured put",
                "underlying_price": 200.0,
                "data_type": "delayed",
                "assumptions": {
                    "dte_range": "20-45 天",
                    "delta_range": "|delta| 0.15-0.30",
                    "min_oi": 100,
                    "min_volume": 10,
                },
                "candidates": [
                    {
                        "expiry": "20260515",
                        "right": "Put",
                        "strike": 180.0,
                        "bid": 1.2,
                        "ask": 1.4,
                        "mid": 1.3,
                        "delta": -0.22,
                        "iv_pct": 28.5,
                        "dte": 29,
                        "oi": 888,
                        "volume": 77,
                        "annual_yield_pct": 9.1,
                    }
                ],
                "total_found": 1,
                "risk_note": "只读",
            }
        )
        self.assertIn("AAPL", rendered)
        self.assertIn("Top 候选", rendered)
        self.assertIn("20260515", rendered)

    @patch("ibkr.options._get_portfolio_snapshot")
    @patch("ibkr.options.get_option_chain")
    def test_short_put_scan_applies_cash_constraint(self, mock_chain, mock_snapshot):
        mock_snapshot.return_value = {
            "accounts": [
                {
                    "base_currency": "USD",
                    "cash_balances": [{"currency": "USD", "ending_cash": 15000}],
                    "positions": [],
                }
            ]
        }
        mock_chain.return_value = {
            "symbol": "AAPL",
            "underlying_price": 200.0,
            "data_type": "delayed",
            "greeks_available": True,
            "greeks_note": None,
            "contracts": [
                {
                    "right": "Put",
                    "strike": 140.0,
                    "mid": 1.2,
                    "delta": -0.2,
                    "oi": 200,
                    "volume": 30,
                    "annual_yield_pct": 8.0,
                },
                {
                    "right": "Put",
                    "strike": 160.0,
                    "mid": 1.5,
                    "delta": -0.21,
                    "oi": 200,
                    "volume": 30,
                    "annual_yield_pct": 8.5,
                },
            ],
        }

        result = scan_short_put_candidates("AAPL")
        self.assertEqual(result["total_found"], 1)
        self.assertEqual(result["candidates"][0]["strike"], 140.0)
        self.assertEqual(result["candidates"][0]["max_contracts_by_cash"], 1)

    @patch("ibkr.options._get_portfolio_snapshot")
    @patch("ibkr.options.get_option_chain")
    def test_covered_call_scan_requires_held_shares(self, mock_chain, mock_snapshot):
        mock_snapshot.return_value = {
            "accounts": [
                {
                    "base_currency": "USD",
                    "cash_balances": [{"currency": "USD", "ending_cash": 1000}],
                    "positions": [
                        {"symbol": "AAPL", "asset_category": "STK", "quantity": 90}
                    ],
                }
            ]
        }
        mock_chain.return_value = {
            "symbol": "AAPL",
            "underlying_price": 200.0,
            "data_type": "delayed",
            "greeks_available": True,
            "greeks_note": None,
            "contracts": [
                {
                    "right": "Call",
                    "strike": 220.0,
                    "mid": 1.1,
                    "delta": 0.18,
                    "oi": 100,
                    "volume": 20,
                    "annual_yield_pct": 7.0,
                }
            ],
        }

        result = scan_covered_call_candidates("AAPL")
        self.assertEqual(result["total_found"], 0)
        self.assertEqual(result["account_context"]["max_covered_calls"], 0)

    @patch("ibkr.options._get_portfolio_snapshot")
    @patch("ibkr.options.get_option_chain")
    def test_short_put_scan_enforces_single_stock_weight_limit(self, mock_chain, mock_snapshot):
        mock_snapshot.return_value = {
            "accounts": [
                {
                    "base_currency": "USD",
                    "summary": {"net_liquidation": 40000},
                    "cash_balances": [{"currency": "USD", "ending_cash": 50000}],
                    "positions": [
                        {
                            "symbol": "AAPL",
                            "asset_category": "STK",
                            "quantity": 100,
                            "market_value_base": 1000,
                        }
                    ],
                }
            ]
        }
        mock_chain.return_value = {
            "symbol": "AAPL",
            "underlying_price": 200.0,
            "data_type": "delayed",
            "greeks_available": True,
            "greeks_note": None,
            "contracts": [
                {
                    "expiry": "20260515",
                    "right": "Put",
                    "strike": 70.0,
                    "mid": 1.2,
                    "delta": -0.2,
                    "oi": 200,
                    "volume": 30,
                    "annual_yield_pct": 8.0,
                },
                {
                    "expiry": "20260515",
                    "right": "Put",
                    "strike": 100.0,
                    "mid": 1.1,
                    "delta": -0.21,
                    "oi": 200,
                    "volume": 30,
                    "annual_yield_pct": 7.5,
                },
            ],
        }

        result = scan_short_put_candidates("AAPL")
        self.assertEqual(result["total_found"], 1)
        self.assertEqual(result["candidates"][0]["strike"], 70.0)
        self.assertEqual(result["candidates"][0]["projected_weight_pct"], 20.0)

    @patch("ibkr.options._get_portfolio_snapshot")
    @patch("ibkr.options.get_option_chain")
    def test_short_put_scan_limits_candidates_per_expiry(self, mock_chain, mock_snapshot):
        mock_snapshot.return_value = {
            "accounts": [
                {
                    "base_currency": "USD",
                    "summary": {"net_liquidation": 100000},
                    "cash_balances": [{"currency": "USD", "ending_cash": 100000}],
                    "positions": [],
                }
            ]
        }
        mock_chain.return_value = {
            "symbol": "AAPL",
            "underlying_price": 200.0,
            "data_type": "delayed",
            "greeks_available": True,
            "greeks_note": None,
            "contracts": [
                {"expiry": "20260515", "right": "Put", "strike": 150.0, "mid": 1.8, "delta": -0.20, "oi": 200, "volume": 30, "annual_yield_pct": 9.0},
                {"expiry": "20260515", "right": "Put", "strike": 148.0, "mid": 1.7, "delta": -0.19, "oi": 200, "volume": 30, "annual_yield_pct": 8.8},
                {"expiry": "20260515", "right": "Put", "strike": 146.0, "mid": 1.6, "delta": -0.18, "oi": 200, "volume": 30, "annual_yield_pct": 8.6},
            ],
        }

        result = scan_short_put_candidates("AAPL")
        self.assertEqual(result["total_found"], 2)
        self.assertEqual([c["strike"] for c in result["candidates"]], [150.0, 148.0])


if __name__ == "__main__":
    unittest.main()

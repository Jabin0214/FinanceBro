# FinanceBro Portfolio Brief, Risk, and Report Design

## Goal

Improve the non-TWS parts of FinanceBro so it becomes useful as a daily portfolio check-in tool before IBKR Gateway and options workflows are ready.

This iteration depends only on IBKR Flex Query data. It does not connect to IB Gateway/TWS, fetch option chains, place orders, or add persistent memory.

## Product Scope

The first deliverable is a shared portfolio summary layer used by three product surfaces:

1. `/brief` in Telegram for a fast one-screen account overview.
2. `/risk` for risk analysis grounded in deterministic Python metrics before Grok adds market context.
3. `/report` HTML output with the same summary and risk flags as Telegram.

The existing natural-language chat should also understand daily portfolio overview requests better by exposing the brief capability as a Claude tool.

## Non-Goals

- No IBKR TWS or IB Gateway dependency.
- No option-chain lookup or option strategy scanning in this iteration.
- No order placement, order preview, cancellation, or modification.
- No SQLite or cross-day memory. That remains the next major track.
- No historical portfolio-change comparison, because current data has only the latest Flex snapshot.

## Data Source

All calculations start from the existing `fetch_flex_report()` shape:

- `accounts[].summary.net_liquidation`
- `accounts[].summary.stock_value_base`
- `accounts[].summary.cash_base`
- `accounts[].summary.total_unrealized_pnl_base`
- `accounts[].summary.total_cost_base`
- `accounts[].summary.total_unrealized_pnl_pct`
- `accounts[].positions[]`
- `accounts[].cash_balances[]`

The implementation should reuse the existing portfolio cache in `agent.tools` where appropriate so `/brief`, `/risk`, `/report`, and chat tool calls do not repeatedly pull Flex data within the cache TTL.

## Shared Summary Module

Add a shared module, tentatively `agent/portfolio_summary.py`, that accepts parsed Flex data and returns a deterministic summary dict.

Responsibilities:

- Consolidate accounts only when all accounts use the same base currency.
- Preserve per-account metrics when base currencies differ.
- Compute total net liquidation, stock value, cash, unrealized P/L, total cost, and unrealized P/L percent.
- Compute equity ratio, cash ratio, other-assets ratio, largest-position weight, and top-5 concentration.
- Produce top holdings, top winners, and top losers.
- Produce risk flags with stable levels: `good`, `warn`, `danger`.
- Produce short Chinese labels and explanations for Telegram/report consumption.

The module should not call Anthropic, Grok, Telegram, IBKR APIs, or write files.

### Risk Flag Rules

Initial thresholds should be simple and explicit:

- Largest single holding:
  - `good`: below 10%
  - `warn`: 10% to below 20%
  - `danger`: 20% or above
- Top-5 concentration:
  - `good`: below 35%
  - `warn`: 35% to below 55%
  - `danger`: 55% or above
- Cash ratio:
  - `danger`: below 8%
  - `warn`: 8% to below 18%
  - `good`: 18% or above

These are portfolio-structure flags, not investment advice. Telegram copy should describe them as observation prompts, not trade instructions.

### Multi-Currency Rule

If accounts have different base currencies, the summary must not add net liquidation, P/L, or cash across accounts. In that case:

- `can_consolidate` is false.
- Combined total fields are disabled or marked unavailable.
- Per-account sections remain available.
- The user-facing text clearly says cross-account ratios are disabled to avoid mixing base currencies.

## Telegram `/brief`

Add a `/brief` command.

Expected behavior:

- Verify the Telegram user is allowed.
- Send a short status message while fetching Flex data.
- Fetch/cached portfolio data.
- Build the shared summary.
- Reply with one or more Telegram HTML messages under the existing `_split()` limit.
- Use only Telegram-safe HTML tags already allowed by the app.

Suggested output structure:

1. Header with report date and base currency.
2. Total assets, cash, stock value, and unrealized P/L.
3. Risk lights for cash buffer, concentration, and largest position.
4. Top holdings by weight.
5. Top winners and top losers by unrealized P/L percent.
6. A short note that values are based on the latest IBKR Flex snapshot.

The command should be fast and deterministic. It should not call Grok.

## Chat Tool

Add a Claude tool, tentatively `get_portfolio_brief`, for natural-language questions such as:

- "今天账户怎么样？"
- "给我看一下组合概览"
- "现在风险灯怎么样？"
- "哪些仓位最拖后腿？"

The tool returns JSON from the shared summary module. The orchestrator prompt should tell Claude to use this tool for summary-style questions and `get_risk_analysis` for deeper risk interpretation.

## `/risk` Enhancement

Keep `/risk` as the deeper, slower analysis path.

Change the deterministic pre-analysis so Grok receives:

- Existing risk metrics from `agent.risk_calculator.compute_metrics`.
- New summary risk flags from the shared summary module.
- Top holdings, winners, losers, cash ratio, and concentration levels.

The user-visible `/risk` output should still be written by Grok, but it should be anchored by the deterministic summary so it is less likely to ignore obvious account-structure issues.

If `GROK_API_KEY` is missing or Grok fails, `/risk` should still return a local fallback summary with risk flags instead of only an error.

## HTML Report

The current HTML report already has useful private summary logic in `report/html_report.py`. Move or mirror that logic through the shared summary module so `/brief` and `/report` use the same calculations.

The report should continue to include:

- Hero summary.
- Metric cards.
- Risk cards.
- Allocation bars.
- Per-account snapshots.
- Top holdings.
- Full holdings.
- Cash balances.

The implementation should avoid a visual redesign in this iteration. The priority is calculation consistency and a clearer top summary.

## Error Experience

Improve user-facing errors around the new surfaces:

- Flex Query configuration missing: tell the user which env vars are required.
- Flex request/download failure: say the IBKR report could not be fetched and suggest retrying later.
- Empty portfolio data: say no valid holdings were found.
- Multi-base-currency accounts: explain that combined totals are disabled rather than failing.
- Grok unavailable during `/risk`: return local risk flags and say market-context analysis is temporarily unavailable.

Errors should stay concise and Telegram-friendly.

## Testing

Add focused tests for the shared summary module and formatting helpers.

Minimum coverage:

- Single-account summary with positions and cash.
- Multi-account same-base-currency consolidation.
- Multi-account different-base-currency degradation.
- Risk threshold boundaries for cash ratio, largest holding, and top-5 concentration.
- Top winners and losers ordering.
- Empty portfolio handling.
- Telegram brief formatting does not exceed message limits when split.

Tests should use static sample dicts and should not call IBKR, Telegram, Anthropic, or Grok.

## Acceptance Criteria

- `/brief` is available in Telegram and returns a useful portfolio overview without calling Grok.
- `/start` mentions `/brief`.
- Natural-language portfolio overview requests can call the brief tool.
- `/risk` includes deterministic risk flags in its analysis context and has a local fallback when Grok is unavailable.
- HTML report calculations come from the shared summary logic or match it exactly.
- Existing `/report`, `/risk`, `/clear`, and chat behavior remain intact.
- Unit tests cover the new shared summary behavior.

## Implementation Order

1. Add shared portfolio summary module with tests.
2. Add Telegram brief formatter and `/brief` command.
3. Add Claude `get_portfolio_brief` tool and prompt guidance.
4. Feed summary flags into `/risk` and add a local fallback.
5. Refactor HTML report summary calculations to use shared summary data.
6. Run unit tests and a syntax/import check.


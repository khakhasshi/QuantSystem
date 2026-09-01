# QuantSystem Backtest Lab

Backtrader-powered local web service for daily A-share and US-stock strategy backtests.

## Data Source

The service opens DuckDB in read-only mode:

```bash
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/duckdb/data/quantsystem.duckdb
```

It reads `daily_bars` and `v_daily_bars_summary` for:

- `ashare` with `qfq` and `unadjusted`
- `usstock` with `qfq` and `unadjusted`

A-share `qfq` is AKShare factor reconstruction. US `qfq` is Yahoo/yfinance adjusted OHLC. Current HS300 and S&P 500 memberships are not point-in-time constituent histories, so strategy output is suitable for local research and tooling smoke tests, not survivorship-bias-free production evidence.

## Start

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem/backtest
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

Optional DeepSeek evaluator:

```bash
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_MODEL="deepseek-v4-flash"
python server.py
```

Open:

```text
http://127.0.0.1:10110
```

The static page can also be opened directly from `backtest/static/index.html`; in that mode it loads local `styles.css` and `app.js`, then calls the running API at `http://127.0.0.1:10110`.

Use another port:

```bash
PORT=10111 python server.py
```

## API

- `GET /api/health`
- `GET /api/meta`
- `GET /api/templates`
- `GET /api/symbols?market=ashare&adjustment=qfq&q=600000&limit=20`
- `GET /api/bars?market=usstock&adjustment=qfq&symbol=AAPL.US&start_date=2020-01-01&end_date=2026-08-25`
- `POST /api/dsl/validate`
- `POST /api/backtest`
- `POST /api/optimize`
- `GET /api/llm/status`
- `POST /api/llm/evaluate`

Example:

```bash
curl -s http://127.0.0.1:10110/api/backtest \
  -H 'Content-Type: application/json' \
  -d '{
    "market": "usstock",
    "adjustment": "qfq",
    "symbol": "AAPL.US",
    "start_date": "2020-01-01",
    "end_date": "2026-08-25",
    "entry_expression": "cross_over(sma(close, 5), sma(close, 20))",
    "exit_expression": "cross_under(sma(close, 5), sma(close, 20))",
    "initial_capital": 100000,
    "fee_bps": 1,
    "target_percent": 0.98,
    "capacity_participation": 0.05,
    "monte_carlo_runs": 300,
    "walk_forward_window": 504,
    "walk_forward_step": 252
  }'
```

Parameter optimization example:

```bash
curl -s http://127.0.0.1:10110/api/optimize \
  -H 'Content-Type: application/json' \
  -d '{
    "market": "usstock",
    "adjustment": "qfq",
    "symbol": "AAPL.US",
    "start_date": "2020-01-01",
    "end_date": "2021-12-31",
    "template_key": "dual_ma",
    "x_param": "fast",
    "y_param": "slow",
    "ranges": {
      "fast": {"min": 3, "max": 30, "step": 3},
      "slow": {"min": 20, "max": 120, "step": 10}
    },
    "objective": "sharpe",
    "initial_capital": 100000,
    "fee_bps": 1,
    "target_percent": 0.98,
    "capacity_participation": 0.05,
    "max_combinations": 400
  }'
```

## DSL

Series:

- `open`, `high`, `low`, `close`, `volume`, `amount`

Functions:

- `sma(series, period)`, `ma(series, period)`, `ema(series, period)`
- `rsi(series, period)`, `std(series, period)`
- `rolling_max(series, period)`, `rolling_min(series, period)`
- `shift(series, periods)`, `pct_change(series, periods)`
- `cross_over(left, right)`, `cross_under(left, right)`
- `abs(series)`, `log(series)`, `sqrt(series)`

Built-in templates:

- Dual moving average: `cross_over(sma(close, 5), sma(close, 20))` / `cross_under(sma(close, 5), sma(close, 20))`
- Bollinger mean reversion
- Bollinger breakout
- RSI reversal

Execution convention:

- Signals are generated from close of bar `t`.
- Backtrader market orders execute on the next bar, normally the open of `t+1`.
- The equity curve is mark-to-market from Backtrader broker value.
- Outputs include final equity, total/annualized return, annualized volatility, Sharpe, Sortino, Calmar, maximum drawdown, win rate, profit factor, trade count, signal count, equity curve, and trade details.

## Turnover, Capacity, And Robustness

The backtest response also includes:

- Turnover: total filled notional divided by average equity, plus annualized turnover.
- Trading cost: total filled commissions, cost drag versus initial capital, and realized bps on filled notional.
- Capacity: uses `amount` when available, otherwise `close * volume`; default capacity is `P20 daily traded value * 5% / target_percent`.
- Fill participation: each executed fill is compared with that day's traded value; `max_fill_participation` is reported in metrics.
- Monte Carlo shuffle: daily strategy returns are reshuffled without replacement to estimate path-dependent drawdown ranges.
- Walk-forward windows: the same DSL strategy is rerun across rolling windows to show period stability; each window automatically prepends DSL indicator warmup bars, so a 125-bar evaluation window can still use expressions such as `sma(close, 140)`.

The web page renders:

- A strategy-parameter optimization panel with configurable two-axis ranges.
- A heatmap of different parameter combinations for Sharpe, Calmar, return, or drawdown objectives.
- A ranked parameter table with return, risk, turnover, and cost columns; the best row can be applied back into the DSL inputs.
- A floating DeepSeek evaluator panel with expand/collapse, local backtest history, one-click replay, optional thinking mode, and Markdown-rendered evaluation output.
- Monte Carlo terminal-return distribution chart.
- Walk-forward stability chart with return bars and drawdown line.
- Strategy detail table and a `复制表格` button that copies the table as Markdown.

LLM notes:

- The default evaluator model is `deepseek-v4-flash`.
- `DEEPSEEK_API_KEY` can be supplied as a server environment variable.
- The floating panel also accepts a temporary API Key stored only in browser `sessionStorage`.
- Thinking mode switches the default model to `deepseek-reasoner` and asks for a deeper audit summary without rendering hidden chain-of-thought.

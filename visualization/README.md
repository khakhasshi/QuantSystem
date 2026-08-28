# QuantSystem Visualization

Local browser service for exploring the daily A-share and US stock datasets already loaded into DuckDB.

## Data Source

The service opens DuckDB in read-only mode:

```bash
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/duckdb/data/quantsystem.duckdb
```

It reads `daily_bars` and `v_daily_bars_summary`. The source directories behind that DuckDB store are:

- `/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/daily/adjustment=unadjusted/daily.parquet`
- `/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/daily/adjustment=qfq/daily.parquet`
- `/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/canonical/daily/adjustment=unadjusted/daily.parquet`
- `/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/canonical/daily/adjustment=qfq/daily.parquet`

A-share `qfq` is AKShare factor reconstruction. US `qfq` is Yahoo/yfinance adjusted OHLC.

## Start

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem/visualization
python3 -m uvicorn server:app --host 127.0.0.1 --port 1010
```

On macOS, ports below `1024` usually require elevated privileges. If `1010` is rejected with `permission denied`, either run with `sudo` or use a high local port:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem/visualization
PORT=10100 python3 server.py
```

Open:

```text
http://127.0.0.1:1010
```

Or, when using the high-port fallback:

```text
http://127.0.0.1:10100
```

## API

- `GET /api/health`
- `GET /api/meta`
- `GET /api/symbols?market=ashare&adjustment=qfq&q=000001&limit=20`
- `GET /api/bars?market=usstock&adjustment=qfq&symbol=AAPL.US&start_date=2020-01-01&end_date=2026-08-25`

The UI uses TradingView Lightweight Charts from the public CDN.

## Indicators

The browser calculates optional indicators from the currently loaded visible bars:

- `MA5`, `MA20`, `MA60`, `MA200`
- `EMA5`, `EMA20`, `EMA60`, `EMA200`
- Bollinger Bands: `BOLL(20, 2)`
- MACD: `MACD(5, 10, 3)`
- RSI: `RSI(14)`

For visual QA or demos, open all indicators at once:

```text
http://127.0.0.1:10100/?indicators=all
```

## Backtesting

The page includes a client-side long-only backtest module. It uses the selected market, adjustment, symbol, start date, and end date from the chart controls.

Strategies:

- Dual moving average crossover: buy on golden cross, sell on death cross.
- Bollinger mean reversion: buy below lower band, sell on return to middle band.
- Bollinger breakout: buy above upper band, sell below middle band.

Execution convention:

- Signals are generated from the close of bar `t`.
- Orders execute at the open of bar `t+1`.
- The final open position, if any, is closed on the final bar's close.
- Single-side fee is configurable in basis points.

Outputs:

- Equity curve.
- Strategy return, annualized return, win rate, profit factor, Sharpe ratio, and trade count.
- Detailed trade blotter with entry/exit dates, prices, shares, fees, P&L, return, holding bars, and exit reason.

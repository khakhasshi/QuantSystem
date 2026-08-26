# US Stock Data Center

This directory owns US stock data acquisition and normalization. The downloader fetches the current S&P 500 constituent cross-section and ten calendar years of daily bars through yfinance.

## Install

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 -m venv datacenter/usstock/.venv
datacenter/usstock/.venv/bin/python -m pip install -r datacenter/usstock/requirements.txt
```

## Run

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py
```

Useful options:

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --asof-date 20260826 \
  --end-date 20260826 \
  --years 10 \
  --adjustments unadjusted,qfq \
  --force
```

For a small connectivity smoke test:

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --symbol-limit 3 \
  --allow-partial \
  --no-parquet
```

To use a custom current constituent file instead of the default S&P 500 table:

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --constituents-csv /path/to/constituents.csv
```

The custom CSV must contain a `Symbol`, `Ticker`, `symbol`, or `ticker` column.

Use `--asof-date` when the constituent cross-section date differs from the completed daily-bar end date. For example, during the 2026-08-26 US session, use `--asof-date 20260826 --start-date 20160826 --end-date 20260825` to keep today's constituent snapshot while excluding the unfinished 2026-08-26 daily bar.

## Output Layout

All generated data stays under `datacenter/usstock/data/` and is ignored by Git.

```text
data/
  raw/
    constituents/universe=sp500/asof=YYYYMMDD/constituents_raw.csv
    yfinance/download/adjustment=unadjusted/symbol=AAPL.US/AAPL_US.csv
    yfinance/download/adjustment=qfq/symbol=AAPL.US/AAPL_US.csv
  metadata/
    sp500_constituents_asof_YYYYMMDD.csv
  canonical/
    daily/adjustment=unadjusted/daily.csv
    daily/adjustment=unadjusted/daily.parquet
    daily/adjustment=qfq/daily.csv
    daily/adjustment=qfq/daily.parquet
  manifests/
    sp500_daily_run_YYYYMMDD.manifest.json
    sp500_daily_unadjusted_YYYYMMDD.manifest.json
    sp500_daily_qfq_YYYYMMDD.manifest.json
```

## Canonical Schema

The standardized daily files use these fixed columns:

```text
trade_date, symbol, ticker, yahoo_symbol, exchange, open, high, low, close,
adj_close, volume, dividends, stock_splits, adjustment, source
```

Notes:

- `symbol` is `AAPL.US` / `BRK.B.US` style.
- `yahoo_symbol` converts dotted share classes to Yahoo format, for example `BRK.B` -> `BRK-B`.
- `trade_date` is ISO `YYYY-MM-DD`.
- `adjustment=unadjusted` calls `yfinance.download(..., auto_adjust=False)` and keeps the provider's raw OHLC plus `adj_close`.
- `adjustment=qfq` calls `yfinance.download(..., auto_adjust=True)`. yfinance adjusts OHLC using Yahoo's adjusted-close methodology, which is the closest provider-native equivalent to current-price-anchored forward-adjusted daily bars.

## Provider APIs

- Constituents: `requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")` then `pandas.read_html(...)`
- Daily bars: `yfinance.download(symbol, start="YYYY-MM-DD", end="YYYY-MM-DD", interval="1d", auto_adjust=...)`

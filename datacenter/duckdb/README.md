# QuantSystem DuckDB Store

This directory wraps the local A-share and US stock daily datasets in one DuckDB database.

Default database:

```bash
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/duckdb/data/quantsystem.duckdb
```

## What Is Loaded

The store loads four canonical Parquet datasets:

- A-share HS300 unadjusted: `datacenter/ashare/data/canonical/daily/adjustment=unadjusted/daily.parquet`
- A-share HS300 qfq: `datacenter/ashare/data/canonical/daily/adjustment=qfq/daily.parquet`
- US S&P 500 unadjusted: `datacenter/usstock/data/canonical/daily/adjustment=unadjusted/daily.parquet`
- US S&P 500 qfq: `datacenter/usstock/data/canonical/daily/adjustment=qfq/daily.parquet`

The adjustment semantics come from the source `agent.md` files:

- A-share qfq is rebuilt from AKShare unadjusted bars plus qfq factors.
- US qfq is Yahoo/yfinance auto-adjusted OHLC, used as the local forward-adjusted research series.

## Tables And Views

`daily_bars` is the unified physical table. Its key is:

```text
market, adjustment, symbol, trade_date
```

Views:

- `v_daily_bars_summary`
- `v_ashare_daily`
- `v_usstock_daily`

Audit tables:

- `ingest_runs`
- `downloader_runs`

## Commands

Initialize schema:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 datacenter/duckdb/duckdb_market_store.py init
```

Load all four existing Parquet datasets:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 datacenter/duckdb/duckdb_market_store.py full-reload
```

Print coverage:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 datacenter/duckdb/duckdb_market_store.py summary
```

Run due increments:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 datacenter/duckdb/duckdb_market_store.py incremental
```

Dry-run due increments:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 datacenter/duckdb/duckdb_market_store.py incremental --dry-run
```

## Daily Incremental Schedule

The launchd template runs the incremental command at:

- `06:30` Asia/Shanghai, after the regular US close has passed in New York.
- `17:30` Asia/Shanghai, after the regular A-share close.

The command itself checks the latest `daily_bars.trade_date` and the market-specific close cutoff before downloading. If the store is current, it records no new rows.

The template lives at:

```bash
datacenter/duckdb/launchd/com.quantsystem.duckdb-incremental.plist
```

Install manually when you want the local Mac to run it:

```bash
cp datacenter/duckdb/launchd/com.quantsystem.duckdb-incremental.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.quantsystem.duckdb-incremental.plist
```

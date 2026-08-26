# DuckDB Data Agent Guide

Scope:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/duckdb
```

This component packages four local canonical daily datasets into DuckDB and integrates the existing market downloaders for incremental updates. Keep DuckDB code, config, staging output, launchd templates, and audit logs inside this directory unless the user changes the scope.

## Source Boundaries

Read these handoff files before changing data semantics:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/agent.md
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/agent.md
```

Loaded datasets:

```text
ashare / hs300_daily / unadjusted
ashare / hs300_daily / qfq
usstock / sp500_daily / unadjusted
usstock / sp500_daily / qfq
```

Do not collapse `adjustment` out of the key. Adjusted and unadjusted rows share `(symbol, trade_date)`.

## Main Files

```text
duckdb_market_store.py
config.json
requirements.txt
README.md
tests/test_duckdb_market_store.py
launchd/com.quantsystem.duckdb-incremental.plist
```

Generated local artifacts are ignored:

```text
data/
staging/
logs/
```

## Database

Default database:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/duckdb/data/quantsystem.duckdb
```

Physical fact table:

```text
daily_bars
```

Primary logical key:

```text
market, adjustment, symbol, trade_date
```

DuckDB does not enforce that key here; the incremental merge deletes matching incoming keys before insert.

Useful views:

```text
v_daily_bars_summary
v_ashare_daily
v_usstock_daily
```

Audit tables:

```text
ingest_runs
downloader_runs
```

## Incremental Update

The wrapper checks the latest stored `trade_date` per market. If new dates are due, it calls the source downloader into:

```text
datacenter/duckdb/staging/<market>/<START>_<END>/
```

Then it merges the staging canonical Parquet rows into `daily_bars`.

Default close cutoffs in `config.json`:

```text
ashare  Asia/Shanghai     17:30
usstock America/New_York  17:30
```

The launchd template runs at `06:30` and `17:30` Asia/Shanghai. The Python command still performs due checks, so repeated runs should be idempotent.

## Verification

Run:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 -m pytest -q datacenter/duckdb/tests
python3 datacenter/duckdb/duckdb_market_store.py summary
```

If source downloader code changes, also run the corresponding source tests:

```bash
datacenter/ashare/.venv/bin/python -m pytest -q datacenter/ashare/tests
datacenter/usstock/.venv/bin/python -m pytest -q datacenter/usstock/tests
```

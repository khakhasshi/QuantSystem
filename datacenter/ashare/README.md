# A-share Data Center

This directory owns A-share data acquisition and normalization. The HS300 daily downloader uses AKShare to fetch the current CSI 300 constituents and ten calendar years of daily bars for both unadjusted and qfq price series.

## Install

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 -m venv datacenter/ashare/.venv
datacenter/ashare/.venv/bin/python -m pip install -r datacenter/ashare/requirements.txt
```

## Run

```bash
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py
```

Useful options:

```bash
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py \
  --end-date 20260826 \
  --years 10 \
  --adjustments unadjusted,qfq \
  --force
```

For a small connectivity smoke test:

```bash
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py --symbol-limit 3 --allow-partial
```

## Output Layout

All generated data stays under `datacenter/ashare/data/` and is ignored by Git.

```text
data/
  raw/
    akshare/
      index_stock_cons_csindex/index=000300/asof=YYYYMMDD/constituents.csv
      stock_zh_a_daily/adjustment=unadjusted/start=YYYYMMDD/end=YYYYMMDD/symbol=600000.SH/600000_SH.csv
      stock_zh_a_daily/adjustment=unadjusted/start=YYYYMMDD/end=YYYYMMDD/symbol=600000.SH/600000_SH.source.json
      stock_zh_a_daily/adjustment=qfq-factor/start=YYYYMMDD/end=YYYYMMDD/symbol=600000.SH/600000_SH.csv
      stock_zh_a_daily/adjustment=qfq-factor/start=YYYYMMDD/end=YYYYMMDD/symbol=600000.SH/600000_SH.source.json
  metadata/
    hs300_constituents_asof_YYYYMMDD.csv
  canonical/
    daily/adjustment=unadjusted/daily.csv
    daily/adjustment=unadjusted/daily.parquet
    daily/adjustment=qfq/daily.csv
    daily/adjustment=qfq/daily.parquet
  manifests/
    hs300_daily_run_YYYYMMDD.manifest.json
    hs300_daily_unadjusted_YYYYMMDD.manifest.json
    hs300_daily_qfq_YYYYMMDD.manifest.json
```

## Canonical Schema

The standardized daily files use these fixed columns:

```text
trade_date, symbol, ticker, exchange, open, high, low, close, volume, amount,
amplitude, pct_change, change, turnover, adjustment, source
```

Notes:

- `symbol` is `000001.SZ` / `600000.SH` style.
- `trade_date` is ISO `YYYY-MM-DD`.
- AKShare A-share `成交量` is in lots, so canonical `volume` is converted to shares by multiplying by 100.
- `amount` is kept as AKShare's `成交额`, denominated in CNY.
- `adjustment=unadjusted` calls `stock_zh_a_hist(..., adjust="")`.
- `adjustment=qfq` defaults to factor reconstruction: unadjusted OHLC divided by AKShare `qfq-factor`, preserving the unadjusted trading-date index.
- `source` records the actual AKShare function or reconstruction path used.

## Provider APIs

- Constituents: `akshare.index_stock_cons_csindex(symbol="000300")`
- Daily bars: `akshare.stock_zh_a_hist(symbol="600000", period="daily", start_date="YYYYMMDD", end_date="YYYYMMDD", adjust="qfq")`
- Fallback daily bars: `akshare.stock_zh_a_daily(symbol="sh600000", start_date="YYYYMMDD", end_date="YYYYMMDD", adjust="qfq")`
- QFQ factors: `akshare.stock_zh_a_daily(symbol="sh600000", adjust="qfq-factor")`

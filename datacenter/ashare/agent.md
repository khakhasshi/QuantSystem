# A-share HS300 Data Agent Guide

This document is for future agents working with the local HS300 daily and minute datasets in this directory. It explains what has already been downloaded, where the files are, what the canonical schemas mean, and how to verify or rebuild the data without guessing.

## Scope

All A-share components for this project live under:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare
```

Do not create A-share code, configs, data manifests, or helper scripts outside this directory unless the user explicitly changes the scope.

The real downloaded data is under:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data
```

`data/`, `.venv/`, and Python caches are ignored by `datacenter/ashare/.gitignore`; code and documentation are intended to be tracked, but downloaded market data is not.

## Daily Dataset Summary

Dataset:

```text
hs300_daily
```

Index universe:

```text
Current CSI 300 / 沪深 300 constituents from AKShare index_stock_cons_csindex(symbol="000300")
```

As-of date and download window:

```text
Constituent as-of date: 2026-08-26
Daily bar window:       2016-08-26 to 2026-08-26
Symbols:                300
```

There are two canonical daily datasets:

```text
unadjusted
qfq
```

Final validated counts:

```text
unadjusted rows: 653,133
qfq rows:        653,133
symbols:         300 / 300 in both datasets
date range:      2016-08-26 to 2026-08-26 in both datasets
duplicate keys:  0 in both datasets
failed symbols:  0 in both datasets
```

The final run manifest is:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/manifests/hs300_daily_run_20260826.manifest.json
```

Read this manifest first when auditing or handing off the data.

## Minute Dataset Summary

Dataset:

```text
hs300_minute_1m
```

Index universe:

```text
Current CSI 300 / 沪深 300 constituents from AKShare index_stock_cons_csindex(symbol="000300")
```

Requested window:

```text
2016-08-28 09:30:00 to 2026-08-28 15:00:00
```

Actual AKShare/Sina coverage downloaded:

```text
2026-08-17 13:48:00 to 2026-08-27 15:00:00
```

Important: the minute dataset is not ten years of history. The downloader requested a ten-year window, but AKShare's available free Sina 1-minute endpoint returned a recent fixed-length window only. This limitation is recorded in the minute manifest as `provider_covered_requested_start=false`.

There are two canonical minute datasets:

```text
unadjusted
qfq
```

Final validated minute counts:

```text
unadjusted rows: 591,000
qfq rows:        591,000
symbols:         300 / 300 in both datasets
rows per symbol: 1,970 in both datasets
timestamp range: 2026-08-17 13:48:00 to 2026-08-27 15:00:00
duplicate keys:  0 in both datasets
failed symbols:  0 in both datasets
```

The final minute run manifest is:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/manifests/hs300_minute_1m_run_20260828.manifest.json
```

Read this manifest before treating the minute data as complete.

## Canonical Files

Use Parquet by default for research code. CSV is provided for inspection and compatibility.

Unadjusted:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/daily/adjustment=unadjusted/daily.parquet
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/daily/adjustment=unadjusted/daily.csv
```

QFQ:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/daily/adjustment=qfq/daily.parquet
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/daily/adjustment=qfq/daily.csv
```

Both canonical datasets have the same `(symbol, trade_date)` key set. This was checked after the qfq factor reconstruction.

Minute unadjusted:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/minute/period=1/adjustment=unadjusted/minute.parquet
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/minute/period=1/adjustment=unadjusted/minute.csv
```

Minute QFQ:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/minute/period=1/adjustment=qfq/minute.parquet
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/canonical/minute/period=1/adjustment=qfq/minute.csv
```

Both canonical minute datasets have the same `(symbol, timestamp)` key set.

## Raw Files

Raw HS300 constituents:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/raw/akshare/index_stock_cons_csindex/index=000300/asof=20260826/constituents.csv
```

Canonical metadata derived from constituents:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/metadata/hs300_constituents_asof_20260826.csv
```

Raw unadjusted daily bars, one CSV per stock:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/raw/akshare/stock_zh_a_daily/adjustment=unadjusted/start=20160826/end=20260826/symbol=<SYMBOL>/<SYMBOL_WITH_UNDERSCORE>.csv
```

Example:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/raw/akshare/stock_zh_a_daily/adjustment=unadjusted/start=20160826/end=20260826/symbol=000001.SZ/000001_SZ.csv
```

Raw qfq adjustment factors, one CSV per stock:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/raw/akshare/stock_zh_a_daily/adjustment=qfq-factor/start=20160826/end=20260826/symbol=<SYMBOL>/<SYMBOL_WITH_UNDERSCORE>.csv
```

Each raw per-symbol CSV has a sidecar `.source.json` with the actual provider, configured provider, symbol, adjustment, and requested date range.

Expected raw file counts for the final dataset:

```text
raw unadjusted CSV files: 300
raw qfq-factor CSV files: 300
```

There are also older smoke-test files and manifests for `20240110`; do not treat them as the production run.

Raw unadjusted 1-minute bars, one CSV per stock:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/raw/akshare/stock_zh_a_minute/period=1/adjustment=unadjusted/start=20160828T093000/end=20260828T150000/symbol=<SYMBOL>/<SYMBOL_WITH_UNDERSCORE>.csv
```

Raw qfq factors used for minute qfq reconstruction, one CSV per stock:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data/raw/akshare/stock_zh_a_daily/adjustment=qfq-factor/asof=20260828/symbol=<SYMBOL>/<SYMBOL_WITH_UNDERSCORE>.csv
```

Expected raw file counts for the final minute dataset:

```text
raw minute unadjusted CSV files: 300
raw qfq-factor CSV files:        300
```

## Daily Canonical Schema

Both canonical datasets use the same fixed columns:

```text
trade_date
symbol
ticker
exchange
open
high
low
close
volume
amount
amplitude
pct_change
change
turnover
adjustment
source
```

Column meanings:

```text
trade_date  ISO date string, YYYY-MM-DD.
symbol      Canonical market symbol, e.g. 000001.SZ or 600000.SH.
ticker      Six-digit stock code, e.g. 000001.
exchange    SH, SZ, BJ, or UNKNOWN. HS300 should be SH/SZ.
open        Daily open price for the selected adjustment.
high        Daily high price for the selected adjustment.
low         Daily low price for the selected adjustment.
close       Daily close price for the selected adjustment.
volume      Shares. Not lots.
amount      CNY traded amount from AKShare.
amplitude   AKShare amplitude field when available. May be null for stock_zh_a_daily.
pct_change  AKShare daily percentage change field when available. May be null for stock_zh_a_daily.
change      AKShare daily absolute price change field when available. May be null for stock_zh_a_daily.
turnover    Percentage points, e.g. 0.5969 means 0.5969 percent.
adjustment  unadjusted or qfq.
source      Actual source or reconstruction path.
```

Important schema detail:

```text
volume is canonicalized to shares.
```

For the final production data, `stock_zh_a_daily` already returned `volume` in shares, so no lot-to-share multiplication was applied. If a future agent uses `stock_zh_a_hist`, that provider returns A-share volume in lots; the downloader multiplies by 100 during normalization.

## Adjustment Policy

Unadjusted canonical data:

```text
source = akshare.stock_zh_a_daily
```

QFQ canonical data:

```text
source = akshare.stock_zh_a_daily+qfq_factor
```

The qfq dataset is not the direct `adjust="qfq"` output from `stock_zh_a_daily`. It is reconstructed as:

```text
qfq_open  = unadjusted_open  / qfq_factor
qfq_high  = unadjusted_high  / qfq_factor
qfq_low   = unadjusted_low   / qfq_factor
qfq_close = unadjusted_close / qfq_factor
```

The reconstructed prices are rounded to 2 decimals to match A-share quote precision.

Why this matters:

During live troubleshooting, direct qfq downloads from `stock_zh_a_daily` had edge-case date loss or date-boundary issues around early post-restructuring rows for at least:

```text
002558.SZ 2016-09-22
002602.SZ 2016-09-12
```

Using unadjusted bars plus qfq factors preserves the unadjusted trading-date index. After reconstruction, `unadjusted` and `qfq` have exactly the same `(symbol, trade_date)` keys.

## Minute Canonical Schema

The standardized minute files use these fixed columns:

```text
timestamp
trade_date
symbol
ticker
exchange
open
high
low
close
volume
amount
adjustment
source
```

Column meanings:

```text
timestamp   Local China market timestamp, YYYY-MM-DD HH:MM:SS.
trade_date  ISO date string, YYYY-MM-DD.
symbol      Canonical market symbol, e.g. 000001.SZ or 600000.SH.
ticker      Six-digit stock code, e.g. 000001.
exchange    SH, SZ, BJ, or UNKNOWN. HS300 should be SH/SZ.
open        1-minute open price for the selected adjustment.
high        1-minute high price for the selected adjustment.
low         1-minute low price for the selected adjustment.
close       1-minute close price for the selected adjustment.
volume      Shares.
amount      CNY traded amount from AKShare/Sina.
adjustment  unadjusted or qfq.
source      Actual source or reconstruction path.
```

Minute unadjusted canonical data:

```text
source = akshare.stock_zh_a_minute
```

Minute qfq canonical data:

```text
source = akshare.stock_zh_a_minute+qfq_factor
```

Minute qfq is reconstructed as:

```text
qfq_open  = unadjusted_minute_open  / qfq_factor_by_trade_date
qfq_high  = unadjusted_minute_high  / qfq_factor_by_trade_date
qfq_low   = unadjusted_minute_low   / qfq_factor_by_trade_date
qfq_close = unadjusted_minute_close / qfq_factor_by_trade_date
```

Minute reconstructed prices are rounded to 6 decimals to reduce intraday return rounding noise. Volume and amount are not adjusted.

## Downloaders

Daily script:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/akshare_hs300_daily.py
```

Default behavior:

```text
provider = stock_zh_a_daily
qfq_mode = factor
adjustments = unadjusted,qfq
root = datacenter/ashare/data
```

The production command used to build the final two canonical datasets from cached raw files was:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py \
  --start-date 20160826 \
  --end-date 20260826 \
  --provider stock_zh_a_daily \
  --qfq-mode factor \
  --adjustments unadjusted,qfq \
  --allow-partial \
  --sleep-seconds 0.0
```

To redownload all raw data from AKShare, add `--force` and use a small sleep to be kinder to the provider:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py \
  --start-date 20160826 \
  --end-date 20260826 \
  --provider stock_zh_a_daily \
  --qfq-mode factor \
  --adjustments unadjusted,qfq \
  --allow-partial \
  --sleep-seconds 0.2 \
  --force
```

For a small smoke test:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py \
  --start-date 20240101 \
  --end-date 20240110 \
  --symbol-limit 1 \
  --allow-partial \
  --force
```

Minute script:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/akshare_hs300_minute.py
```

Minute default behavior:

```text
provider = stock_zh_a_minute
qfq_mode = factor
period = 1
adjustments = unadjusted,qfq
root = datacenter/ashare/data
```

The production command used to build the minute datasets was:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_minute.py \
  --start-datetime '2016-08-28 09:30:00' \
  --end-datetime '2026-08-28 15:00:00' \
  --adjustments unadjusted,qfq \
  --allow-partial \
  --sleep-seconds 0.1 \
  --force
```

The command completes successfully for all 300 symbols, but the manifest records that the provider did not cover the requested start.

## Environment

The local virtual environment is:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/.venv
```

Dependencies are listed in:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/requirements.txt
```

Recreate the environment if needed:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
uv venv --python /opt/homebrew/bin/python3.13 datacenter/ashare/.venv
uv pip install --python datacenter/ashare/.venv/bin/python -r datacenter/ashare/requirements.txt
```

Do not assume system Python has `akshare` or `pandas`; the original system Python did not.

## Quick Read Examples

Read both canonical datasets:

```python
from pathlib import Path
import pandas as pd

root = Path("/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/ashare/data")

unadjusted = pd.read_parquet(root / "canonical/daily/adjustment=unadjusted/daily.parquet")
qfq = pd.read_parquet(root / "canonical/daily/adjustment=qfq/daily.parquet")

print(unadjusted.shape)
print(qfq.shape)
print(unadjusted.head())
print(qfq.head())
```

Load one symbol:

```python
symbol = "000001.SZ"
u = unadjusted[unadjusted["symbol"].eq(symbol)].sort_values("trade_date")
q = qfq[qfq["symbol"].eq(symbol)].sort_values("trade_date")
```

Build a close-price panel:

```python
close_panel = (
    qfq.pivot(index="trade_date", columns="symbol", values="close")
    .sort_index()
)
```

Check aligned keys:

```python
u_keys = set(map(tuple, unadjusted[["symbol", "trade_date"]].to_numpy()))
q_keys = set(map(tuple, qfq[["symbol", "trade_date"]].to_numpy()))
assert u_keys == q_keys
```

## Verification Commands

Run unit tests:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/ashare/.venv/bin/python -m pytest -q datacenter/ashare/tests
```

Expected result at handoff:

```text
9 passed
```

Run a data audit:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/ashare/.venv/bin/python - <<'PY'
from pathlib import Path
import json
import pandas as pd

root = Path("datacenter/ashare/data")
manifest = json.loads((root / "manifests/hs300_daily_run_20260826.manifest.json").read_text())
print(json.dumps(manifest["adjustments"], ensure_ascii=False, indent=2))

frames = {}
for adj in ["unadjusted", "qfq"]:
    df = pd.read_parquet(root / "canonical/daily" / f"adjustment={adj}" / "daily.parquet")
    frames[adj] = df
    print(adj, df.shape, df["symbol"].nunique(), df["trade_date"].min(), df["trade_date"].max())
    print("duplicates", int(df.duplicated(["symbol", "trade_date"]).sum()))
    print("core nulls", int(df[["trade_date", "symbol", "open", "high", "low", "close", "volume", "amount"]].isna().sum().sum()))

u_keys = set(map(tuple, frames["unadjusted"][["symbol", "trade_date"]].to_numpy()))
q_keys = set(map(tuple, frames["qfq"][["symbol", "trade_date"]].to_numpy()))
print("key equality", u_keys == q_keys)
PY
```

Expected high-level output:

```text
unadjusted (653133, 16) 300 2016-08-26 2026-08-26
qfq        (653133, 16) 300 2016-08-26 2026-08-26
duplicates 0
core nulls 0
key equality True
```

Count raw files:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
find datacenter/ashare/data/raw/akshare/stock_zh_a_daily/adjustment=unadjusted/start=20160826/end=20260826 -name '*.csv' | wc -l
find datacenter/ashare/data/raw/akshare/stock_zh_a_daily/adjustment=qfq-factor/start=20160826/end=20260826 -name '*.csv' | wc -l
```

Expected:

```text
300
300
```

Run a minute data audit:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/ashare/.venv/bin/python - <<'PY'
from pathlib import Path
import json
import pandas as pd

root = Path("datacenter/ashare/data")
manifest = json.loads((root / "manifests/hs300_minute_1m_run_20260828.manifest.json").read_text())
print(json.dumps(manifest["adjustments"], ensure_ascii=False, indent=2))

frames = {}
for adj in ["unadjusted", "qfq"]:
    df = pd.read_parquet(root / "canonical/minute/period=1" / f"adjustment={adj}" / "minute.parquet")
    frames[adj] = df
    print(adj, df.shape, df["symbol"].nunique(), df["timestamp"].min(), df["timestamp"].max())
    print("duplicates", int(df.duplicated(["symbol", "timestamp"]).sum()))
    print("core nulls", int(df[["timestamp", "trade_date", "symbol", "open", "high", "low", "close", "volume", "amount"]].isna().sum().sum()))
    print("rows per symbol min/max", int(df.groupby("symbol").size().min()), int(df.groupby("symbol").size().max()))

u_keys = set(map(tuple, frames["unadjusted"][["symbol", "timestamp"]].to_numpy()))
q_keys = set(map(tuple, frames["qfq"][["symbol", "timestamp"]].to_numpy()))
print("key equality", u_keys == q_keys)
PY
```

Expected high-level output:

```text
unadjusted (591000, 13) 300 2026-08-17 13:48:00 2026-08-27 15:00:00
qfq        (591000, 13) 300 2026-08-17 13:48:00 2026-08-27 15:00:00
duplicates 0
core nulls 0
rows per symbol min/max 1970 1970
key equality True
```

## Known Provider Behavior

Observed during download on 2026-08-26:

```text
akshare.stock_zh_a_hist
```

repeatedly failed in this environment with remote disconnections from the Eastmoney endpoint. The script still supports it through `--provider auto`, but the production data used:

```text
akshare.stock_zh_a_daily
```

`stock_zh_a_daily` direct qfq was not used for final canonical qfq because direct qfq showed early-boundary row issues for special names. Use the factor-rebuilt qfq unless the user explicitly asks for direct provider qfq comparison.

Observed during minute download on 2026-08-28:

```text
akshare.stock_zh_a_hist_min_em
```

failed in this environment with remote disconnections from the Eastmoney endpoint.

```text
akshare.stock_zh_a_minute
```

worked, but only returned a recent fixed-length 1-minute window. The downloaded minute snapshot covers `2026-08-17 13:48:00` through `2026-08-27 15:00:00`, even though the requested window started on `2016-08-28 09:30:00`.

AKShare's own documentation describes `stock_zh_a_minute` as a Sina minute interface for 1, 5, 15, 30, and 60 minute data. The local AKShare 1.18.94 implementation requests `datalen=1970`; attempts to increase this through the underlying Sina URL returned empty data in this environment.

## Research Usage Notes

This dataset is current-HS300, not point-in-time HS300 membership. It is suitable for current-universe research, loader tests, schema integration, and local factor pipeline smoke work. It is not a survivorship-bias-free historical index constituent dataset.

For factor research:

```text
Use qfq prices for return calculation unless testing execution on unadjusted raw market prices.
Use unadjusted prices for raw price/volume/amount sanity checks and corporate-action diagnostics.
Do not infer tradability solely from rows existing in the dataset.
Do not forward-fill missing stock bars without an explicit trading-calendar policy.
```

The daily canonical datasets do not include index benchmark bars, limit-up/down flags, suspensions, ST status, corporate-action details, or trading-calendar annotations. The minute canonical datasets add recent 1-minute bars only; they are not suitable as a ten-year intraday research corpus.

## Files Added For This Component

Code and documentation:

```text
datacenter/ashare/.gitignore
datacenter/ashare/README.md
datacenter/ashare/__init__.py
datacenter/ashare/akshare_hs300_daily.py
datacenter/ashare/akshare_hs300_minute.py
datacenter/ashare/agent.md
datacenter/ashare/requirements.txt
datacenter/ashare/tests/test_akshare_hs300_daily.py
datacenter/ashare/tests/test_akshare_hs300_minute.py
```

Generated local artifacts:

```text
datacenter/ashare/.venv/
datacenter/ashare/data/
datacenter/ashare/__pycache__/
datacenter/ashare/tests/__pycache__/
```

Only the generated local artifacts are ignored by Git.

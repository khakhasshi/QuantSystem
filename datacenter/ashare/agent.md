# A-share HS300 Daily Data Agent Guide

This document is for future agents working with the two local HS300 daily datasets in this directory. It explains what has already been downloaded, where the files are, what the canonical schema means, and how to verify or rebuild the data without guessing.

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

## Dataset Summary

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

## Canonical Schema

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

## Downloader

Main script:

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
6 passed
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

## Research Usage Notes

This dataset is current-HS300, not point-in-time HS300 membership. It is suitable for current-universe research, loader tests, schema integration, and local factor pipeline smoke work. It is not a survivorship-bias-free historical index constituent dataset.

For factor research:

```text
Use qfq prices for return calculation unless testing execution on unadjusted raw market prices.
Use unadjusted prices for raw price/volume/amount sanity checks and corporate-action diagnostics.
Do not infer tradability solely from rows existing in the dataset.
Do not forward-fill missing stock bars without an explicit trading-calendar policy.
```

The canonical datasets are daily bars only. They do not include minute bars, index benchmark bars, limit-up/down flags, suspensions, ST status, corporate-action details, or trading-calendar annotations.

## Files Added For This Component

Code and documentation:

```text
datacenter/ashare/.gitignore
datacenter/ashare/README.md
datacenter/ashare/__init__.py
datacenter/ashare/akshare_hs300_daily.py
datacenter/ashare/agent.md
datacenter/ashare/requirements.txt
datacenter/ashare/tests/test_akshare_hs300_daily.py
```

Generated local artifacts:

```text
datacenter/ashare/.venv/
datacenter/ashare/data/
datacenter/ashare/__pycache__/
datacenter/ashare/tests/__pycache__/
```

Only the generated local artifacts are ignored by Git.


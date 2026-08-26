# Agent Handoff: US Stock Daily Data

This document is the handoff note for future agents working with the local US stock daily datasets under:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/
```

The data has already been downloaded locally. Prefer reading the canonical Parquet files first. Use CSV only when a downstream tool cannot read Parquet.

## Current Dataset Snapshot

Dataset name: `sp500_daily`

Universe: current S&P 500 constituent cross-section

Constituent snapshot date: `2026-08-26`

Daily bar window: `2016-08-26` through `2026-08-25`

Reason the daily bar end date is `2026-08-25`: the data was finalized on `2026-08-26` Asia/Shanghai time while the US `2026-08-26` session could be incomplete. The canonical datasets intentionally exclude unfinished `2026-08-26` daily bars.

Provider:

- Constituents: Wikipedia S&P 500 constituent table, fetched by `requests.get(...)` then parsed with `pandas.read_html(...)`
- Daily bars: `yfinance.download(...)`

Coverage after final local audit:

```text
adjustment=unadjusted
  rows: 1,225,694
  symbols: 503
  min_trade_date: 2016-08-26
  max_trade_date: 2026-08-25
  duplicate symbol/date rows: 0
  failed symbols: 0

adjustment=qfq
  rows: 1,225,694
  symbols: 503
  min_trade_date: 2016-08-26
  max_trade_date: 2026-08-25
  duplicate symbol/date rows: 0
  failed symbols: 0
```

Raw yfinance files are also present:

```text
adjustment=unadjusted raw files: 503
adjustment=qfq raw files: 503
```

## Canonical Data Paths

Use these files for analysis:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/canonical/daily/adjustment=unadjusted/daily.parquet
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/canonical/daily/adjustment=qfq/daily.parquet
```

CSV mirrors:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/canonical/daily/adjustment=unadjusted/daily.csv
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/canonical/daily/adjustment=qfq/daily.csv
```

File sizes from the final audit:

```text
unadjusted daily.parquet: 31,366,284 bytes
unadjusted daily.csv:     222,737,229 bytes
qfq daily.parquet:        50,728,988 bytes
qfq daily.csv:            215,793,594 bytes
```

## Metadata And Manifests

Current constituent metadata:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/metadata/sp500_constituents_asof_20260826.csv
```

Final clean run manifest:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/manifests/sp500_daily_run_20260825.manifest.json
```

Adjustment-specific manifests:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/manifests/sp500_daily_unadjusted_20260825.manifest.json
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/manifests/sp500_daily_qfq_20260825.manifest.json
```

There may also be older manifest files with suffix `20260826` from an earlier full run. Do not treat those as the finalized analysis boundary because the qfq run briefly included a `2026-08-26` provider row during the live US session. The finalized canonical files and finalized manifests use historical end date `20260825`.

## Schema

Both canonical datasets have the same columns:

```text
trade_date
symbol
ticker
yahoo_symbol
exchange
open
high
low
close
adj_close
volume
dividends
stock_splits
adjustment
source
```

Column meanings:

```text
trade_date    ISO date, YYYY-MM-DD.
symbol        Internal canonical symbol, for example AAPL.US or BRK.B.US.
ticker        Original US ticker from the constituent table, for example BRK.B.
yahoo_symbol  Yahoo Finance symbol, for example BRK-B.
exchange      Currently always US.
open          Daily open.
high          Daily high.
low           Daily low.
close         Daily close.
adj_close     Adjusted close. In qfq data this is set equal to close because yfinance already adjusted OHLC.
volume        Daily share volume.
dividends     Dividend action value reported by yfinance.
stock_splits  Split action value reported by yfinance.
adjustment    Either unadjusted or qfq.
source        yfinance call mode used to build the row.
```

## Adjustment Semantics

There are two canonical datasets.

`adjustment=unadjusted`:

- Built from `yfinance.download(..., auto_adjust=False)`.
- OHLC are provider raw OHLC.
- `adj_close` is Yahoo's adjusted close.
- Use this when raw historical prices are required, for example event studies around splits/dividends, raw execution-price simulations, or reconciliation to unadjusted provider bars.

`adjustment=qfq`:

- Built from `yfinance.download(..., auto_adjust=True)`.
- yfinance adjusts OHLC using Yahoo's adjusted-close methodology.
- `adj_close` is set equal to `close` in canonical output because the OHLC series is already adjusted.
- This is the closest yfinance-native equivalent to current-price-anchored forward-adjusted daily bars.
- Use this for factor research that needs continuous adjusted price series.

Important: yfinance does not expose an exchange-native Chinese-style `qfq` flag. The local name `qfq` means "Yahoo auto-adjusted OHLC, treated as forward-adjusted for research continuity." Do not present it as an official exchange adjustment.

## Data Boundary And Caveats

This is a current-constituent snapshot dataset, not a point-in-time historical index-membership dataset.

Implications:

- The 503 symbols are the S&P 500 constituents as captured on `2026-08-26`.
- The 10-year historical bars are fetched for those current constituents.
- This introduces survivorship/current-membership bias if used as historical S&P 500 membership.
- Do not use this as PIT index backtest membership without a separate historical constituent table.
- Delisted former S&P 500 members are not included unless they are in the current snapshot.
- yfinance is a research data provider, not an official exchange feed.

For causal backtests:

- Use `trade_date` as the bar date.
- Do not trade on the same bar's close unless your strategy explicitly models close-time availability.
- If generating signals at close `t`, execute no earlier than a defined next executable price, commonly open `t+1`.
- Include transaction costs, slippage, corporate action handling, missing data rules, and liquidity filters explicitly.
- Record `NO_TRADE` when the data is insufficient rather than forcing a signal.

## Raw Data Layout

Raw constituent snapshot:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/raw/constituents/universe=sp500/asof=20260826/constituents_raw.csv
```

Raw yfinance files:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/raw/yfinance/download/adjustment=unadjusted/symbol=AAPL.US/AAPL_US.csv
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/raw/yfinance/download/adjustment=qfq/symbol=AAPL.US/AAPL_US.csv
```

Pattern:

```text
data/raw/yfinance/download/adjustment=<unadjusted|qfq>/symbol=<SYMBOL>/<SAFE_SYMBOL>.csv
```

Use raw files for provider-level debugging or rebuilding canonical outputs. Use canonical files for normal analysis.

## How To Load The Data

Python example:

```python
from pathlib import Path
import pandas as pd

root = Path("/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data")

unadjusted = pd.read_parquet(root / "canonical/daily/adjustment=unadjusted/daily.parquet")
qfq = pd.read_parquet(root / "canonical/daily/adjustment=qfq/daily.parquet")

print(unadjusted.shape, qfq.shape)
print(unadjusted["trade_date"].min(), unadjusted["trade_date"].max())
print(qfq["trade_date"].min(), qfq["trade_date"].max())
```

Memory-conscious read:

```python
import pandas as pd

path = "/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data/canonical/daily/adjustment=qfq/daily.parquet"
df = pd.read_parquet(path, columns=["trade_date", "symbol", "open", "high", "low", "close", "volume"])
```

Filter one symbol:

```python
aapl = df.loc[df["symbol"].eq("AAPL.US")].sort_values("trade_date")
```

## Quick Local Audit

Run this before relying on the data in a new agent session:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/usstock/.venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd

root = Path("/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/data")
for adj in ["unadjusted", "qfq"]:
    path = root / "canonical" / "daily" / f"adjustment={adj}" / "daily.parquet"
    df = pd.read_parquet(path, columns=["trade_date", "symbol"])
    print(adj)
    print("  path:", path)
    print("  rows:", len(df))
    print("  symbols:", df["symbol"].nunique())
    print("  min_trade_date:", df["trade_date"].min())
    print("  max_trade_date:", df["trade_date"].max())
    print("  duplicate_symbol_trade_date_rows:", df.duplicated(["symbol", "trade_date"]).sum())
PY
```

Expected output:

```text
unadjusted
  rows: 1225694
  symbols: 503
  min_trade_date: 2016-08-26
  max_trade_date: 2026-08-25
  duplicate_symbol_trade_date_rows: 0
qfq
  rows: 1225694
  symbols: 503
  min_trade_date: 2016-08-26
  max_trade_date: 2026-08-25
  duplicate_symbol_trade_date_rows: 0
```

Check raw file counts:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
find datacenter/usstock/data/raw/yfinance/download/adjustment=unadjusted -name '*.csv' | wc -l
find datacenter/usstock/data/raw/yfinance/download/adjustment=qfq -name '*.csv' | wc -l
wc -l datacenter/usstock/data/metadata/sp500_constituents_asof_20260826.csv
```

Expected:

```text
503
503
504
```

The metadata file has 504 lines because it includes a header plus 503 constituents.

## Downloader

Main script:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/yfinance_index_daily.py
```

Install dependencies:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
python3 -m venv datacenter/usstock/.venv
datacenter/usstock/.venv/bin/python -m pip install -r datacenter/usstock/requirements.txt
```

The environment already exists locally at:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/.venv
```

Run tests:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/usstock/.venv/bin/python -m pytest -q datacenter/usstock/tests
```

Expected current result:

```text
7 passed
```

## Rebuilding Canonical From Existing Raw

If raw files already exist and you only need to rebuild canonical outputs, do not pass `--force`.

Finalized rebuild command used for this dataset:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --asof-date 2026-08-26 \
  --start-date 2016-08-26 \
  --end-date 2026-08-25 \
  --allow-partial \
  --sleep-seconds 0
```

This reads existing raw yfinance CSVs when present, rebuilds both canonical datasets, and writes manifests with suffix `20260825`.

## Full Redownload

Only redownload when you explicitly need a fresh provider snapshot.

Example:

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --asof-date YYYYMMDD \
  --start-date YYYYMMDD \
  --end-date YYYYMMDD \
  --allow-partial \
  --force \
  --sleep-seconds 0.25
```

Do not run a full redownload during an active US trading session unless you intentionally want live/incomplete current-day data. To avoid unfinished bars, set `--end-date` to the last completed US trading date and set `--asof-date` separately.

## Common Pitfalls

Do not confuse these dates:

```text
asof_date: constituent snapshot date
end_date: final included daily bar date
```

Do not use `sp500_daily_run_20260826.manifest.json` as the final boundary. The clean final boundary is:

```text
sp500_daily_run_20260825.manifest.json
```

Do not assume this is point-in-time S&P 500 membership. It is current members with 10 years of history.

Do not merge `unadjusted` and `qfq` rows without including the `adjustment` column in the key. Both datasets use the same `symbol` and `trade_date` keys.

Do not treat `qfq` prices as executable prices. Use unadjusted bars for execution modeling unless your methodology explicitly operates on adjusted synthetic prices.

Do not edit generated files by hand. Rebuild them from raw files with the downloader.

## Recommended Agent Workflow

1. Read this file and the final manifest.
2. Run the quick local audit.
3. Load Parquet, not CSV, for analysis.
4. Decide whether the task needs raw or adjusted prices.
5. For factor research, use `adjustment=qfq` unless raw corporate-action behavior matters.
6. For execution simulation, use `adjustment=unadjusted`.
7. Document the universe boundary as "current S&P 500 constituents as of 2026-08-26, history from 2016-08-26 to 2026-08-25."
8. If doing backtests, explicitly state the survivorship-bias caveat.
9. If modifying the downloader, run tests and then rerun a small smoke test before full redownload.

## Current Git/Generated-File Note

The data directory is ignored by:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/.gitignore
```

That is intentional. The canonical data and raw yfinance files are local artifacts, not source files. Source files that matter for future agents:

```text
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/yfinance_index_daily.py
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/tests/test_yfinance_index_daily.py
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/requirements.txt
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/README.md
/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/usstock/agent.md
```

# QuantSystem

QuantSystem 是一个本地量化数据工作区，当前由四个子项目组成：

- `datacenter/ashare`: A 股沪深 300 日线下载、清洗、标准化。
- `datacenter/usstock`: 美股 S&P 500 日线下载、清洗、标准化。
- `datacenter/duckdb`: 将 A 股和美股标准化 Parquet 合并进本地 DuckDB，并提供增量更新入口。
- `datacenter/crypto`: 一个本地运行的加密货币实时价格面板，使用交易所 WebSocket 行情。

根目录职责是组织这些数据中心模块。各模块自己的 `README.md` 和 `agent.md` 记录了更细的实现细节；本文件用于快速理解全局结构、数据边界、启动方式、测试方式和日常运维流程。

## 目录结构

```text
/Users/jiangjingzhe/Desktop/QuantSystem
  readme.md
  datacenter/
    ashare/
      akshare_hs300_daily.py
      requirements.txt
      README.md
      agent.md
      tests/
      data/                 # 本地下载数据，已被 .gitignore 忽略
    usstock/
      yfinance_index_daily.py
      requirements.txt
      README.md
      agent.md
      tests/
      data/                 # 本地下载数据，已被 .gitignore 忽略
    duckdb/
      duckdb_market_store.py
      config.json
      requirements.txt
      README.md
      agent.md
      launchd/
      tests/
      data/                 # 本地 DuckDB、审计日志，已被 .gitignore 忽略
      staging/              # 增量下载暂存区，已被 .gitignore 忽略
      logs/                 # launchd 日志目录，已被 .gitignore 忽略
    crypto/
      package.json
      index.html
      src/
        main.js
        styles.css
```

## 当前数据快照

以下覆盖来自本地 DuckDB `v_daily_bars_summary`，反映当前工作区已经落库的数据状态。

| 市场 | 数据集 | 复权口径 | 行数 | 标的数 | 起始交易日 | 最新交易日 | OHLC 空值行 | 重复键行 |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: |
| A 股 | `hs300_daily` | `qfq` | 653,133 | 300 | 2016-08-26 | 2026-08-26 | 0 | 0 |
| A 股 | `hs300_daily` | `unadjusted` | 653,133 | 300 | 2016-08-26 | 2026-08-26 | 0 | 0 |
| 美股 | `sp500_daily` | `qfq` | 1,225,694 | 503 | 2016-08-26 | 2026-08-25 | 0 | 0 |
| 美股 | `sp500_daily` | `unadjusted` | 1,225,694 | 503 | 2016-08-26 | 2026-08-25 | 0 | 0 |

本地主要数据文件：

```text
datacenter/ashare/data/canonical/daily/adjustment=unadjusted/daily.parquet
datacenter/ashare/data/canonical/daily/adjustment=qfq/daily.parquet
datacenter/usstock/data/canonical/daily/adjustment=unadjusted/daily.parquet
datacenter/usstock/data/canonical/daily/adjustment=qfq/daily.parquet
datacenter/duckdb/data/quantsystem.duckdb
```

数据文件和虚拟环境默认不入 Git。代码、配置、测试和文档才是主要可跟踪内容。

## 数据流

```text
AKShare / yfinance
  -> raw per-symbol files
  -> canonical CSV / Parquet
  -> DuckDB daily_bars
  -> research queries / summaries / downstream tools
```

A 股和美股下载器都同时产出两类标准化日线：

- `unadjusted`: 未复权或 provider 原始 OHLC。
- `qfq`: 本项目中的连续调整价格序列。A 股由未复权价格和 qfq 因子重建；美股使用 yfinance `auto_adjust=True` 作为研究用连续价格序列。

DuckDB 统一表的逻辑键是：

```text
market, adjustment, symbol, trade_date
```

不要把 `adjustment` 从键里拿掉。未复权和调整后序列共享同一个 `symbol + trade_date` 空间，但价格语义不同。

## 快速开始

建议从根目录执行命令：

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem
```

### 安装 A 股依赖

```bash
python3 -m venv datacenter/ashare/.venv
datacenter/ashare/.venv/bin/python -m pip install -r datacenter/ashare/requirements.txt
```

### 安装美股依赖

```bash
python3 -m venv datacenter/usstock/.venv
datacenter/usstock/.venv/bin/python -m pip install -r datacenter/usstock/requirements.txt
```

### 安装 DuckDB 依赖

DuckDB 模块没有独立 `.venv` 要求；可以使用系统 Python 或你自己的项目虚拟环境：

```bash
python3 -m pip install -r datacenter/duckdb/requirements.txt
```

如果你希望隔离环境，也可以自行建立 `datacenter/duckdb/.venv`，再用该环境执行 `duckdb_market_store.py`。

### 启动加密货币面板

```bash
cd /Users/jiangjingzhe/Desktop/QuantSystem/datacenter/crypto
npm start
```

默认本地地址：

```text
http://127.0.0.1:3411
```

该面板支持 `BTC`、`ETH`、`DOGE`、`SOL`，优先连接 Binance ticker WebSocket，连接异常时切换到 Coinbase ticker WebSocket。

## 子项目说明

### `datacenter/ashare`

A 股模块负责当前沪深 300 成分股的日线数据。

入口脚本：

```text
datacenter/ashare/akshare_hs300_daily.py
```

默认行为：

- 数据源：AKShare。
- 指数成分：`index_stock_cons_csindex(symbol="000300")`。
- 默认窗口：结束日向前 10 个日历年。
- 默认输出：CSV + Parquet。
- 默认复权：`unadjusted,qfq`。
- 产物根目录：`datacenter/ashare/data/`。

常用命令：

```bash
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py
```

指定日期和复权口径：

```bash
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py \
  --end-date 20260826 \
  --years 10 \
  --adjustments unadjusted,qfq \
  --force
```

小样本连通性检查：

```bash
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py \
  --symbol-limit 3 \
  --allow-partial
```

核心标准化字段：

```text
trade_date, symbol, ticker, exchange, open, high, low, close, volume, amount,
amplitude, pct_change, change, turnover, adjustment, source
```

重要语义：

- `symbol` 使用 `000001.SZ`、`600000.SH` 格式。
- `trade_date` 是 ISO 日期字符串。
- `volume` 在 canonical 层统一为股，不是手。
- A 股 `qfq` 当前推荐使用因子重建路径，保留未复权序列的交易日索引。

### `datacenter/usstock`

美股模块负责当前 S&P 500 成分股的日线数据。

入口脚本：

```text
datacenter/usstock/yfinance_index_daily.py
```

默认行为：

- 成分来源：Wikipedia S&P 500 constituent table。
- 日线来源：yfinance。
- 默认窗口：结束日向前 10 个日历年。
- 默认输出：CSV + Parquet。
- 默认复权：`unadjusted,qfq`。
- 产物根目录：`datacenter/usstock/data/`。

常用命令：

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py
```

指定成分 as-of date、历史窗口和复权口径：

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --asof-date 20260826 \
  --end-date 20260825 \
  --years 10 \
  --adjustments unadjusted,qfq \
  --force
```

小样本连通性检查：

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --symbol-limit 3 \
  --allow-partial \
  --no-parquet
```

使用自定义成分 CSV：

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --constituents-csv /path/to/constituents.csv
```

自定义 CSV 需要包含 `Symbol`、`Ticker`、`symbol` 或 `ticker` 列。

核心标准化字段：

```text
trade_date, symbol, ticker, yahoo_symbol, exchange, open, high, low, close,
adj_close, volume, dividends, stock_splits, adjustment, source
```

重要语义：

- `symbol` 使用 `AAPL.US`、`BRK.B.US` 格式。
- `yahoo_symbol` 会把 `BRK.B` 转为 Yahoo 使用的 `BRK-B`。
- `unadjusted` 来自 `yfinance.download(..., auto_adjust=False)`。
- `qfq` 来自 `yfinance.download(..., auto_adjust=True)`，是本地研究语义，不是交易所官方“前复权”标记。
- 当前 S&P 500 成分是当前截面，不是点时历史成分，历史回测会有当前成分偏差。

### `datacenter/duckdb`

DuckDB 模块把 A 股和美股四份 canonical Parquet 数据合并到一个本地数据库。

入口脚本：

```text
datacenter/duckdb/duckdb_market_store.py
```

默认数据库：

```text
datacenter/duckdb/data/quantsystem.duckdb
```

主要表和视图：

- `daily_bars`: 统一日线事实表。
- `v_daily_bars_summary`: 行数、标的数、日期范围、空值和重复键摘要。
- `v_ashare_daily`: A 股视图。
- `v_usstock_daily`: 美股视图。
- `ingest_runs`: 入库审计表。
- `downloader_runs`: 增量下载审计表。

初始化 schema：

```bash
python3 datacenter/duckdb/duckdb_market_store.py init
```

全量重载已有 Parquet：

```bash
python3 datacenter/duckdb/duckdb_market_store.py full-reload
```

只重载指定市场：

```bash
python3 datacenter/duckdb/duckdb_market_store.py full-reload --markets ashare
python3 datacenter/duckdb/duckdb_market_store.py full-reload --markets usstock
```

查看覆盖：

```bash
python3 datacenter/duckdb/duckdb_market_store.py summary
```

增量更新：

```bash
python3 datacenter/duckdb/duckdb_market_store.py incremental
```

增量 dry-run：

```bash
python3 datacenter/duckdb/duckdb_market_store.py incremental --dry-run
```

增量逻辑：

- 读取 DuckDB 中每个市场的最新 `trade_date`。
- 根据 `config.json` 中的市场时区和收盘后 cutoff 判断目标结束日。
- 如果本地已覆盖到目标结束日，返回 `up_to_date`。
- 如果需要更新，则调用对应市场下载器写入 `datacenter/duckdb/staging/<market>/<START>_<END>/`。
- 然后按 `market + adjustment + symbol + trade_date` 删除旧行并合并新行。

当前默认 cutoff：

| 市场 | 时区 | 收盘后更新阈值 |
| --- | --- | --- |
| `ashare` | `Asia/Shanghai` | `17:30` |
| `usstock` | `America/New_York` | `17:30` |

launchd 模板：

```text
datacenter/duckdb/launchd/com.quantsystem.duckdb-incremental.plist
```

安装到当前 macOS 用户：

```bash
cp datacenter/duckdb/launchd/com.quantsystem.duckdb-incremental.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.quantsystem.duckdb-incremental.plist
```

模板计划在 Asia/Shanghai `06:30` 和 `17:30` 运行。即使重复触发，Python 入口也会再次检查是否真的需要增量。

### `datacenter/crypto`

Crypto 模块是一个本地静态网页，用于显示主流币种实时价格。

文件：

```text
datacenter/crypto/index.html
datacenter/crypto/src/main.js
datacenter/crypto/src/styles.css
datacenter/crypto/package.json
```

功能：

- 币种：`BTC`、`ETH`、`DOGE`、`SOL`。
- 行情源：Binance WebSocket ticker；异常时轮转 Coinbase WebSocket ticker。
- 展示：当前价格、24h 涨跌、24h 高低、24h 成交量、更新时间、实时 sparkline。
- 运行方式：`npm start` 会用 `python3 -m http.server` 在 `127.0.0.1:3411` 提供静态页面。

这个模块当前只是实时展示面板，不向 DuckDB 写入数据，也不产出研究用历史行情。

## 本地数据和版本控制边界

已忽略目录：

- `datacenter/ashare/data/`
- `datacenter/ashare/.venv/`
- `datacenter/usstock/data/`
- `datacenter/usstock/.venv/`
- `datacenter/duckdb/data/`
- `datacenter/duckdb/staging/`
- `datacenter/duckdb/logs/`
- Python cache 和 pytest cache

提交代码时通常应包含：

- 下载器源码。
- DuckDB store 源码。
- 配置文件。
- 测试。
- README / agent handoff 文档。

通常不应提交：

- 本地下载的 CSV / Parquet。
- DuckDB 数据库文件。
- 虚拟环境。
- launchd 运行日志。
- 临时 staging 数据。

## 测试

A 股测试：

```bash
datacenter/ashare/.venv/bin/python -m pytest -q datacenter/ashare/tests
```

美股测试：

```bash
datacenter/usstock/.venv/bin/python -m pytest -q datacenter/usstock/tests
```

DuckDB 测试：

```bash
python3 -m pytest -q datacenter/duckdb/tests
```

全局文档/数据状态核对：

```bash
python3 datacenter/duckdb/duckdb_market_store.py summary
```

如果系统 Python 没有 `duckdb` 或 `pytest`，请先安装：

```bash
python3 -m pip install -r datacenter/duckdb/requirements.txt
```

## 常见工作流

### 重新构建 A 股 canonical 数据

```bash
datacenter/ashare/.venv/bin/python datacenter/ashare/akshare_hs300_daily.py \
  --end-date YYYYMMDD \
  --years 10 \
  --adjustments unadjusted,qfq \
  --force
```

完成后重载 DuckDB：

```bash
python3 datacenter/duckdb/duckdb_market_store.py full-reload --markets ashare
python3 datacenter/duckdb/duckdb_market_store.py summary
```

### 重新构建美股 canonical 数据

如果美股当日常规交易还没结束，不要把未完成日线纳入 canonical。可以使用当日成分截面，但把 `--end-date` 固定在最后一个完整交易日。

```bash
datacenter/usstock/.venv/bin/python datacenter/usstock/yfinance_index_daily.py \
  --asof-date YYYYMMDD \
  --end-date YYYYMMDD \
  --years 10 \
  --adjustments unadjusted,qfq \
  --force
```

完成后重载 DuckDB：

```bash
python3 datacenter/duckdb/duckdb_market_store.py full-reload --markets usstock
python3 datacenter/duckdb/duckdb_market_store.py summary
```

### 每日增量

```bash
python3 datacenter/duckdb/duckdb_market_store.py incremental --dry-run
python3 datacenter/duckdb/duckdb_market_store.py incremental
python3 datacenter/duckdb/duckdb_market_store.py summary
```

增量执行失败时，优先查看：

```text
datacenter/duckdb/data/audit/
datacenter/duckdb/staging/
```

### 查询 DuckDB

Python 示例：

```python
import duckdb

con = duckdb.connect("/Users/jiangjingzhe/Desktop/QuantSystem/datacenter/duckdb/data/quantsystem.duckdb")

summary = con.execute("SELECT * FROM v_daily_bars_summary").fetchdf()
ashare = con.execute("""
    SELECT trade_date, symbol, close
    FROM v_ashare_daily
    WHERE adjustment = 'qfq'
      AND symbol = '000001.SZ'
    ORDER BY trade_date
""").fetchdf()
```

CLI 示例：

```bash
duckdb datacenter/duckdb/data/quantsystem.duckdb
```

进入 DuckDB 后：

```sql
SELECT * FROM v_daily_bars_summary;
SELECT market, adjustment, max(trade_date) FROM daily_bars GROUP BY 1, 2;
```

## 研究使用注意事项

这套数据适合作为本地研究数据底座，但不是直接可交易信号系统。

使用前请明确：

- A 股沪深 300 和美股 S&P 500 都是当前成分截面，不是完整点时历史成分。
- 美股 `qfq` 是 Yahoo/yfinance 自动调整语义，不是交易所官方前复权。
- yfinance 和 AKShare 都是研究数据源，不能替代交易所官方数据或券商成交回报。
- `trade_date` 是行情归属日期，不等于信号可用时间。
- 如果在收盘 `t` 产生信号，回测执行价应明确建模为 `t+1` 可执行价格或其他可证明的成交时点。
- 回测必须显式记录交易成本、滑点、停牌/缺失数据处理、流动性过滤和风险退出。
- 数据不足时应输出 `NO_TRADE` 或跳过样本，不要强行补齐交易结论。

## 维护原则

- 修改数据语义前，先读对应模块的 `agent.md`。
- 先确认当前 `summary`，再改下载器或增量逻辑。
- 大范围重建前，记录使用的 provider、日期窗口、成分 as-of date、复权口径和失败符号。
- 不要把 raw / canonical / DuckDB 数据文件提交进 Git。
- 不要在未完成交易日写入“日线已收盘”的 canonical 数据。
- 保留 manifest 和 audit 记录，它们是之后排查数据差异的主要证据。

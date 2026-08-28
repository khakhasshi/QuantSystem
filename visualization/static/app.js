const state = {
  meta: [],
  symbols: [],
  lastPayload: null,
  priceChart: null,
  candleSeries: null,
  volumeSeries: null,
  priceIndicatorSeries: new Map(),
  macdChart: null,
  macdSeries: null,
  rsiChart: null,
  rsiSeries: null,
  backtestChart: null,
  backtestSeries: null,
  syncingTimeScale: false,
  resizeObserver: null,
};

const els = {
  market: document.querySelector("#marketSelect"),
  adjustment: document.querySelector("#adjustmentSelect"),
  symbol: document.querySelector("#symbolInput"),
  symbolOptions: document.querySelector("#symbolOptions"),
  startDate: document.querySelector("#startDateInput"),
  endDate: document.querySelector("#endDateInput"),
  load: document.querySelector("#loadButton"),
  summary: document.querySelector("#datasetSummary"),
  activeSymbol: document.querySelector("#activeSymbol"),
  coverageRange: document.querySelector("#coverageRange"),
  visibleRange: document.querySelector("#visibleRange"),
  barCount: document.querySelector("#barCount"),
  priceChart: document.querySelector("#priceChart"),
  macdPanel: document.querySelector("#macdPanel"),
  macdChart: document.querySelector("#macdChart"),
  rsiPanel: document.querySelector("#rsiPanel"),
  rsiChart: document.querySelector("#rsiChart"),
  strategy: document.querySelector("#strategySelect"),
  bollingerModeField: document.querySelector("#bollingerModeField"),
  bollingerMode: document.querySelector("#bollingerModeSelect"),
  fastMa: document.querySelector("#fastMaInput"),
  slowMa: document.querySelector("#slowMaInput"),
  bollPeriod: document.querySelector("#bollPeriodInput"),
  bollDev: document.querySelector("#bollDevInput"),
  initialCapital: document.querySelector("#initialCapitalInput"),
  feeBps: document.querySelector("#feeBpsInput"),
  backtestButton: document.querySelector("#backtestButton"),
  backtestChart: document.querySelector("#backtestChart"),
  backtestEmpty: document.querySelector("#backtestEmpty"),
  btReturn: document.querySelector("#btReturn"),
  btAnnualReturn: document.querySelector("#btAnnualReturn"),
  btWinRate: document.querySelector("#btWinRate"),
  btProfitFactor: document.querySelector("#btProfitFactor"),
  btSharpe: document.querySelector("#btSharpe"),
  btTrades: document.querySelector("#btTrades"),
  tradeTableBody: document.querySelector("#tradeTableBody"),
  emptyState: document.querySelector("#emptyState"),
  indicators: [...document.querySelectorAll("[data-indicator]")],
};

const marketLabels = {
  ashare: "A股 HS300",
  usstock: "美股 S&P 500",
};

const adjustmentLabels = {
  qfq: "前复权 / Adjusted",
  unadjusted: "不复权",
};

const indicatorStyles = {
  ma5: { period: 5, label: "MA5", color: "#f08a24", lineWidth: 2 },
  ma20: { period: 20, label: "MA20", color: "#1f78d1", lineWidth: 2 },
  ma60: { period: 60, label: "MA60", color: "#7b5cc7", lineWidth: 2 },
  ma200: { period: 200, label: "MA200", color: "#5f6b7a", lineWidth: 2 },
  ema5: { period: 5, label: "EMA5", color: "#c56a1a", lineWidth: 1, dashed: true },
  ema20: { period: 20, label: "EMA20", color: "#0f8b8d", lineWidth: 1, dashed: true },
  ema60: { period: 60, label: "EMA60", color: "#6d3aa8", lineWidth: 1, dashed: true },
  ema200: { period: 200, label: "EMA200", color: "#2d465f", lineWidth: 1, dashed: true },
};

function qs(params) {
  return new URLSearchParams(params).toString();
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return payload;
}

function chartOptions(container, height) {
  return {
    layout: {
      background: { color: "#ffffff" },
      textColor: "#263241",
      fontFamily: getComputedStyle(document.body).fontFamily,
    },
    grid: {
      vertLines: { color: "#eef2f6" },
      horzLines: { color: "#eef2f6" },
    },
    rightPriceScale: {
      borderColor: "#d9e0ea",
    },
    timeScale: {
      borderColor: "#d9e0ea",
      timeVisible: false,
      secondsVisible: false,
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
    width: container.clientWidth,
    height,
  };
}

function initCharts() {
  state.priceChart = LightweightCharts.createChart(
    els.priceChart,
    chartOptions(els.priceChart, els.priceChart.clientHeight)
  );
  state.candleSeries = state.priceChart.addCandlestickSeries({
    upColor: "#0f8b5f",
    downColor: "#c94c4c",
    borderUpColor: "#0f8b5f",
    borderDownColor: "#c94c4c",
    wickUpColor: "#0f8b5f",
    wickDownColor: "#c94c4c",
  });
  state.volumeSeries = state.priceChart.addHistogramSeries({
    color: "rgba(104, 114, 130, 0.35)",
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
  });
  state.priceChart.priceScale("right").applyOptions({
    scaleMargins: { top: 0.08, bottom: 0.28 },
  });
  state.priceChart.priceScale("volume").applyOptions({
    scaleMargins: { top: 0.78, bottom: 0 },
  });
  bindTimeScaleSync(state.priceChart);

  state.resizeObserver = new ResizeObserver(resizeCharts);
  state.resizeObserver.observe(els.priceChart);
  state.resizeObserver.observe(els.macdChart);
  state.resizeObserver.observe(els.rsiChart);
  state.resizeObserver.observe(els.backtestChart);
}

function resizeCharts() {
  if (state.priceChart) {
    state.priceChart.applyOptions({
      width: els.priceChart.clientWidth,
      height: els.priceChart.clientHeight,
    });
  }
  if (state.macdChart && !els.macdPanel.hidden) {
    state.macdChart.applyOptions({
      width: els.macdChart.clientWidth,
      height: els.macdChart.clientHeight,
    });
  }
  if (state.rsiChart && !els.rsiPanel.hidden) {
    state.rsiChart.applyOptions({
      width: els.rsiChart.clientWidth,
      height: els.rsiChart.clientHeight,
    });
  }
  if (state.backtestChart) {
    state.backtestChart.applyOptions({
      width: els.backtestChart.clientWidth,
      height: els.backtestChart.clientHeight,
    });
  }
}

function bindTimeScaleSync(chart) {
  chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    syncVisibleLogicalRange(chart, range);
  });
}

function activeCharts() {
  return [
    state.priceChart,
    state.macdChart && !els.macdPanel.hidden ? state.macdChart : null,
    state.rsiChart && !els.rsiPanel.hidden ? state.rsiChart : null,
    state.backtestChart ? state.backtestChart : null,
  ].filter(Boolean);
}

function syncVisibleLogicalRange(sourceChart, range) {
  if (!range || state.syncingTimeScale) return;
  state.syncingTimeScale = true;
  for (const chart of activeCharts()) {
    if (chart !== sourceChart) {
      chart.timeScale().setVisibleLogicalRange(range);
    }
  }
  window.requestAnimationFrame(() => {
    state.syncingTimeScale = false;
  });
}

function syncPanelsToPrice() {
  if (!state.priceChart) return;
  const range = state.priceChart.timeScale().getVisibleLogicalRange();
  if (range) {
    syncVisibleLogicalRange(state.priceChart, range);
  }
}

async function loadMeta() {
  const payload = await fetchJson("/api/meta");
  state.meta = payload.summary;
  const fragments = state.meta.map((row) => {
    return `${marketLabels[row.market]} ${adjustmentLabels[row.adjustment]}: ${row.symbols} symbols, ${row.min_trade_date} to ${row.max_trade_date}`;
  });
  els.summary.textContent = fragments.join(" | ");
}

async function loadSymbols({ pickFirst = false } = {}) {
  const payload = await fetchJson(`/api/symbols?${qs({
    market: els.market.value,
    adjustment: els.adjustment.value,
    q: els.symbol.value.trim(),
    limit: 1000,
  })}`);
  state.symbols = payload.symbols;
  els.symbolOptions.replaceChildren(
    ...state.symbols.map((item) => {
      const option = document.createElement("option");
      option.value = item.symbol;
      option.label = `${item.symbol} ${item.ticker || ""} ${item.min_trade_date} to ${item.max_trade_date}`;
      return option;
    })
  );

  const exact = state.symbols.find((item) => item.symbol === els.symbol.value.trim().toUpperCase());
  if (exact) {
    applySymbolBounds(exact);
    return;
  }

  if (pickFirst && state.symbols[0]) {
    els.symbol.value = state.symbols[0].symbol;
    applySymbolBounds(state.symbols[0]);
  }
}

function syncSelectedSymbolBounds() {
  const symbol = els.symbol.value.trim().toUpperCase();
  const selected = state.symbols.find((item) => item.symbol === symbol);
  if (!selected) return;
  applySymbolBounds(selected);
}

function applySymbolBounds(selected) {
  els.startDate.min = selected.min_trade_date;
  els.startDate.max = selected.max_trade_date;
  els.endDate.min = selected.min_trade_date;
  els.endDate.max = selected.max_trade_date;
  if (!els.startDate.value || els.startDate.value < selected.min_trade_date || els.startDate.value > selected.max_trade_date) {
    els.startDate.value = selected.min_trade_date;
  }
  if (!els.endDate.value || els.endDate.value < selected.min_trade_date || els.endDate.value > selected.max_trade_date) {
    els.endDate.value = selected.max_trade_date;
  }
  if (els.startDate.value > els.endDate.value) {
    els.endDate.value = selected.max_trade_date;
  }
}

async function loadBars() {
  const symbol = els.symbol.value.trim().toUpperCase();
  if (!symbol) {
    showEmpty("请选择一个股票代码");
    return;
  }

  setLoading(true);
  try {
    const payload = await fetchJson(`/api/bars?${qs({
      market: els.market.value,
      adjustment: els.adjustment.value,
      symbol,
      start_date: els.startDate.value,
      end_date: els.endDate.value,
    })}`);
    renderBars(payload, { fitContent: true });
    runBacktest();
  } catch (error) {
    showEmpty(error.message);
  } finally {
    setLoading(false);
  }
}

function renderBars(payload, { fitContent = false } = {}) {
  state.lastPayload = payload;
  if (!payload.bars.length) {
    showEmpty("这个起始日期之后没有可展示的K线");
    return;
  }

  els.emptyState.hidden = true;
  const candles = payload.bars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close }));
  const volumes = payload.bars.map((bar) => ({
    time: bar.time,
    value: bar.volume || 0,
    color: bar.close >= bar.open ? "rgba(15, 139, 95, 0.45)" : "rgba(201, 76, 76, 0.45)",
  }));

  els.activeSymbol.textContent = `${payload.symbol} · ${marketLabels[payload.market]} · ${adjustmentLabels[payload.adjustment]}`;
  els.coverageRange.textContent = `${payload.coverage.min_trade_date} 至 ${payload.coverage.max_trade_date}`;
  els.visibleRange.textContent = `${payload.visible.start_date} 至 ${payload.visible.end_date}`;
  els.barCount.textContent = String(payload.visible.rows);

  try {
    state.candleSeries.setData(candles);
    state.volumeSeries.setData(volumes);
    renderPriceIndicators(payload.bars);
    renderMacd(payload.bars);
    renderRsi(payload.bars);
    if (fitContent) {
      state.priceChart.timeScale().fitContent();
    }
    syncPanelsToPrice();
  } catch (error) {
    showEmpty(`图表渲染失败：${error.message || error}`);
  }
}

function runBacktest() {
  if (!state.lastPayload || !state.lastPayload.bars.length) {
    showBacktestEmpty("请先加载K线数据");
    return;
  }
  try {
    const config = readBacktestConfig();
    const result = backtestLongOnly(state.lastPayload.bars, config);
    renderBacktest(result);
  } catch (error) {
    showBacktestEmpty(error.message || String(error));
  }
}

function readBacktestConfig() {
  const strategy = els.strategy.value;
  const initialCapital = readPositiveNumber(els.initialCapital, "初始资金");
  const feeRate = readNumber(els.feeBps, "单边费率bps", 0, 200) / 10000;
  if (strategy === "dual_ma") {
    const fast = Math.floor(readNumber(els.fastMa, "快线周期", 2, 250));
    const slow = Math.floor(readNumber(els.slowMa, "慢线周期", 3, 400));
    if (fast >= slow) throw new Error("双均线要求快线周期小于慢线周期");
    return { strategy, initialCapital, feeRate, fast, slow };
  }
  const period = Math.floor(readNumber(els.bollPeriod, "BOLL周期", 5, 250));
  const deviations = readNumber(els.bollDev, "标准差倍数", 0.5, 5);
  return {
    strategy,
    initialCapital,
    feeRate,
    mode: els.bollingerMode.value,
    period,
    deviations,
  };
}

function readNumber(input, label, min, max) {
  const value = Number(input.value);
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new Error(`${label} 必须在 ${min} 到 ${max} 之间`);
  }
  return value;
}

function readPositiveNumber(input, label) {
  const value = Number(input.value);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} 必须大于 0`);
  }
  return value;
}

function backtestLongOnly(bars, config) {
  if (bars.length < 3) throw new Error("回测区间K线数量不足");
  const orders = config.strategy === "dual_ma" ? dualMaOrders(bars, config) : bollingerOrders(bars, config);
  const orderMap = new Map();
  for (const order of orders) {
    orderMap.set(order.executeIndex, order);
  }

  let cash = config.initialCapital;
  let shares = 0;
  let entry = null;
  const trades = [];
  const markers = [];
  const equity = [{ time: bars[0].time, value: roundValue(config.initialCapital) }];

  for (let i = 1; i < bars.length; i += 1) {
    const order = orderMap.get(i);
    if (order?.target === 1 && shares === 0) {
      const price = Number(bars[i].open);
      shares = cash / (price * (1 + config.feeRate));
      const grossValue = shares * price;
      const fee = grossValue * config.feeRate;
      cash = cash - grossValue - fee;
      entry = {
        entryDate: bars[i].time,
        entrySignalDate: order.signalDate,
        entryPrice: price,
        shares,
        entryFee: fee,
        entryValue: grossValue,
        reason: order.reason,
        entryIndex: i,
      };
      markers.push({ time: bars[i].time, position: "belowBar", color: "#0f8b5f", shape: "arrowUp", text: "BUY" });
    } else if (order?.target === 0 && shares > 0 && entry) {
      const price = Number(bars[i].open);
      const closed = closePosition(entry, bars[i], price, config.feeRate, order.reason, i);
      cash += closed.exitValue - closed.exitFee;
      shares = 0;
      entry = null;
      trades.push(closed.trade);
      markers.push({ time: bars[i].time, position: "aboveBar", color: "#c94c4c", shape: "arrowDown", text: "SELL" });
    }
    equity.push({ time: bars[i].time, value: roundValue(cash + shares * Number(bars[i].close)) });
  }

  if (shares > 0 && entry) {
    const lastIndex = bars.length - 1;
    const lastBar = bars[lastIndex];
    const closed = closePosition(entry, lastBar, Number(lastBar.close), config.feeRate, "期末平仓", lastIndex);
    cash += closed.exitValue - closed.exitFee;
    trades.push(closed.trade);
    markers.push({ time: lastBar.time, position: "aboveBar", color: "#c94c4c", shape: "arrowDown", text: "END" });
    equity[equity.length - 1] = { time: lastBar.time, value: roundValue(cash) };
  }

  const metrics = backtestMetrics(equity, trades, config.initialCapital);
  return { equity, trades, markers, metrics, config };
}

function closePosition(entry, exitBar, exitPrice, feeRate, reason, exitIndex) {
  const exitValue = entry.shares * exitPrice;
  const exitFee = exitValue * feeRate;
  const grossPnl = exitValue - entry.entryValue;
  const totalFee = entry.entryFee + exitFee;
  const netPnl = grossPnl - totalFee;
  const trade = {
    side: "LONG",
    entryDate: entry.entryDate,
    entrySignalDate: entry.entrySignalDate,
    exitDate: exitBar.time,
    entryPrice: entry.entryPrice,
    exitPrice,
    shares: entry.shares,
    grossPnl,
    fee: totalFee,
    netPnl,
    returnPct: netPnl / (entry.entryValue + entry.entryFee),
    holdingBars: exitIndex - entry.entryIndex,
    reason,
  };
  return { exitValue, exitFee, trade };
}

function dualMaOrders(bars, config) {
  const fast = nullableArrayFromPoints(bars, smaPoints(bars, config.fast));
  const slow = nullableArrayFromPoints(bars, smaPoints(bars, config.slow));
  const orders = [];
  let target = 0;
  for (let i = 1; i < bars.length - 1; i += 1) {
    if (fast[i - 1] === null || slow[i - 1] === null || fast[i] === null || slow[i] === null) continue;
    if (target === 0 && fast[i - 1] <= slow[i - 1] && fast[i] > slow[i]) {
      target = 1;
      orders.push({ executeIndex: i + 1, target, signalDate: bars[i].time, reason: `金叉 MA${config.fast}>MA${config.slow}` });
    } else if (target === 1 && fast[i - 1] >= slow[i - 1] && fast[i] < slow[i]) {
      target = 0;
      orders.push({ executeIndex: i + 1, target, signalDate: bars[i].time, reason: `死叉 MA${config.fast}<MA${config.slow}` });
    }
  }
  return orders;
}

function bollingerOrders(bars, config) {
  const bands = bollingerArrays(bars, config.period, config.deviations);
  const orders = [];
  let target = 0;
  for (let i = 1; i < bars.length - 1; i += 1) {
    if (bands.middle[i] === null) continue;
    const close = Number(bars[i].close);
    if (config.mode === "mean_reversion") {
      if (target === 0 && close < bands.lower[i]) {
        target = 1;
        orders.push({ executeIndex: i + 1, target, signalDate: bars[i].time, reason: "低于下轨买入" });
      } else if (target === 1 && close >= bands.middle[i]) {
        target = 0;
        orders.push({ executeIndex: i + 1, target, signalDate: bars[i].time, reason: "回到中轨卖出" });
      }
    } else if (target === 0 && close > bands.upper[i]) {
      target = 1;
      orders.push({ executeIndex: i + 1, target, signalDate: bars[i].time, reason: "突破上轨买入" });
    } else if (target === 1 && close < bands.middle[i]) {
      target = 0;
      orders.push({ executeIndex: i + 1, target, signalDate: bars[i].time, reason: "跌破中轨卖出" });
    }
  }
  return orders;
}

function backtestMetrics(equity, trades, initialCapital) {
  const finalEquity = equity[equity.length - 1]?.value ?? initialCapital;
  const totalReturn = finalEquity / initialCapital - 1;
  const years = Math.max((equity.length - 1) / 252, 1 / 252);
  const annualReturn = finalEquity > 0 ? (finalEquity / initialCapital) ** (1 / years) - 1 : -1;
  const dailyReturns = [];
  for (let i = 1; i < equity.length; i += 1) {
    const prev = equity[i - 1].value;
    if (prev > 0) dailyReturns.push(equity[i].value / prev - 1);
  }
  const sharpe = sharpeRatio(dailyReturns);
  const wins = trades.filter((trade) => trade.netPnl > 0);
  const losses = trades.filter((trade) => trade.netPnl < 0);
  const grossProfit = wins.reduce((sum, trade) => sum + trade.netPnl, 0);
  const grossLoss = Math.abs(losses.reduce((sum, trade) => sum + trade.netPnl, 0));
  return {
    finalEquity,
    totalReturn,
    annualReturn,
    winRate: trades.length ? wins.length / trades.length : null,
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : null,
    sharpe,
    tradeCount: trades.length,
  };
}

function sharpeRatio(returns) {
  if (returns.length < 2) return null;
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1);
  const std = Math.sqrt(variance);
  if (std === 0) return null;
  return (mean / std) * Math.sqrt(252);
}

function renderBacktest(result) {
  ensureBacktestChart();
  els.backtestEmpty.hidden = true;
  state.backtestSeries.setData(result.equity);
  state.backtestChart.timeScale().fitContent();
  syncVisibleLogicalRange(state.backtestChart, state.backtestChart.timeScale().getVisibleLogicalRange());
  state.candleSeries.setMarkers(result.markers);
  renderBacktestMetrics(result.metrics);
  renderTradeTable(result.trades);
}

function ensureBacktestChart() {
  if (state.backtestChart) {
    resizeCharts();
    return;
  }
  state.backtestChart = LightweightCharts.createChart(
    els.backtestChart,
    chartOptions(els.backtestChart, els.backtestChart.clientHeight)
  );
  bindTimeScaleSync(state.backtestChart);
  state.backtestSeries = state.backtestChart.addLineSeries({
    title: "Equity",
    color: "#0f8b8d",
    lineWidth: 2,
    priceLineVisible: false,
  });
}

function renderBacktestMetrics(metrics) {
  els.btReturn.textContent = formatPercent(metrics.totalReturn);
  els.btAnnualReturn.textContent = formatPercent(metrics.annualReturn);
  els.btWinRate.textContent = metrics.winRate === null ? "--" : formatPercent(metrics.winRate);
  els.btProfitFactor.textContent =
    metrics.profitFactor === null ? "--" : metrics.profitFactor === Infinity ? "∞" : formatNumber(metrics.profitFactor, 2);
  els.btSharpe.textContent = metrics.sharpe === null ? "--" : formatNumber(metrics.sharpe, 2);
  els.btTrades.textContent = String(metrics.tradeCount);
}

function renderTradeTable(trades) {
  if (!trades.length) {
    els.tradeTableBody.innerHTML = '<tr><td colspan="12">无已完成交易</td></tr>';
    return;
  }
  els.tradeTableBody.replaceChildren(
    ...trades.map((trade) => {
      const row = document.createElement("tr");
      row.className = trade.netPnl >= 0 ? "trade-win" : "trade-loss";
      const cells = [
        trade.side,
        trade.entryDate,
        trade.exitDate,
        formatNumber(trade.entryPrice, 3),
        formatNumber(trade.exitPrice, 3),
        formatNumber(trade.shares, 2),
        formatCurrency(trade.grossPnl),
        formatCurrency(trade.fee),
        formatCurrency(trade.netPnl),
        formatPercent(trade.returnPct),
        String(trade.holdingBars),
        trade.reason,
      ];
      for (const cell of cells) {
        const td = document.createElement("td");
        td.textContent = cell;
        row.appendChild(td);
      }
      return row;
    })
  );
}

function showBacktestEmpty(message) {
  ensureBacktestChart();
  els.backtestEmpty.textContent = message;
  els.backtestEmpty.hidden = false;
  state.backtestSeries.setData([]);
  state.candleSeries.setMarkers([]);
  renderBacktestMetrics({
    totalReturn: null,
    annualReturn: null,
    winRate: null,
    profitFactor: null,
    sharpe: null,
    tradeCount: 0,
  });
  els.tradeTableBody.innerHTML = '<tr><td colspan="12">--</td></tr>';
}

function renderPriceIndicators(bars) {
  clearPriceIndicators();
  const selected = selectedIndicators();
  for (const key of ["ma5", "ma20", "ma60", "ma200"]) {
    if (!selected.has(key)) continue;
    const style = indicatorStyles[key];
    addPriceLine(key, smaPoints(bars, style.period), style);
  }
  for (const key of ["ema5", "ema20", "ema60", "ema200"]) {
    if (!selected.has(key)) continue;
    const style = indicatorStyles[key];
    addPriceLine(key, emaPoints(bars, style.period), style);
  }
  if (selected.has("bollinger")) {
    const bands = bollingerPoints(bars, 20, 2);
    addPriceLine("bollinger-upper", bands.upper, {
      label: "BOLL U",
      color: "#8e9aaa",
      lineWidth: 1,
      dashed: true,
    });
    addPriceLine("bollinger-middle", bands.middle, {
      label: "BOLL M",
      color: "#718096",
      lineWidth: 1,
    });
    addPriceLine("bollinger-lower", bands.lower, {
      label: "BOLL L",
      color: "#8e9aaa",
      lineWidth: 1,
      dashed: true,
    });
  }
}

function clearPriceIndicators() {
  for (const series of state.priceIndicatorSeries.values()) {
    state.priceChart.removeSeries(series);
  }
  state.priceIndicatorSeries.clear();
}

function addPriceLine(key, data, style) {
  if (!data.length) return;
  const series = state.priceChart.addLineSeries({
    title: style.label,
    color: style.color,
    lineWidth: style.lineWidth,
    lineStyle: style.dashed ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
    priceLineVisible: false,
    lastValueVisible: true,
  });
  series.setData(data);
  state.priceIndicatorSeries.set(key, series);
}

function renderMacd(bars) {
  const enabled = selectedIndicators().has("macd");
  els.macdPanel.hidden = !enabled;
  if (!enabled) return;
  ensureMacdChart();

  const data = macdPoints(bars, 5, 10, 3);
  state.macdSeries.histogram.setData(data.histogram);
  state.macdSeries.macd.setData(data.macd);
  state.macdSeries.signal.setData(data.signal);
  syncPanelsToPrice();
}

function ensureMacdChart() {
  if (state.macdChart) {
    resizeCharts();
    return;
  }
  state.macdChart = LightweightCharts.createChart(
    els.macdChart,
    chartOptions(els.macdChart, els.macdChart.clientHeight)
  );
  bindTimeScaleSync(state.macdChart);
  state.macdSeries = {
    histogram: state.macdChart.addHistogramSeries({
      title: "MACD Hist",
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
      priceLineVisible: false,
    }),
    macd: state.macdChart.addLineSeries({
      title: "DIF",
      color: "#1f78d1",
      lineWidth: 2,
      priceLineVisible: false,
    }),
    signal: state.macdChart.addLineSeries({
      title: "DEA",
      color: "#f08a24",
      lineWidth: 2,
      priceLineVisible: false,
    }),
  };
}

function renderRsi(bars) {
  const enabled = selectedIndicators().has("rsi");
  els.rsiPanel.hidden = !enabled;
  if (!enabled) return;
  ensureRsiChart();

  state.rsiSeries.line.setData(rsiPoints(bars, 14));
  state.rsiSeries.upper.setData(horizontalLinePoints(bars, 70));
  state.rsiSeries.lower.setData(horizontalLinePoints(bars, 30));
  syncPanelsToPrice();
}

function ensureRsiChart() {
  if (state.rsiChart) {
    resizeCharts();
    return;
  }
  state.rsiChart = LightweightCharts.createChart(
    els.rsiChart,
    chartOptions(els.rsiChart, els.rsiChart.clientHeight)
  );
  bindTimeScaleSync(state.rsiChart);
  state.rsiSeries = {
    line: state.rsiChart.addLineSeries({
      title: "RSI",
      color: "#7b5cc7",
      lineWidth: 2,
      priceLineVisible: false,
    }),
    upper: state.rsiChart.addLineSeries({
      title: "70",
      color: "#c94c4c",
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
    }),
    lower: state.rsiChart.addLineSeries({
      title: "30",
      color: "#0f8b5f",
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
    }),
  };
}

function selectedIndicators() {
  return new Set(els.indicators.filter((input) => input.checked).map((input) => input.dataset.indicator));
}

function closeValues(bars) {
  return bars.map((bar) => Number(bar.close));
}

function smaPoints(bars, period) {
  const values = closeValues(bars);
  const points = [];
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) {
      points.push({ time: bars[i].time, value: roundValue(sum / period) });
    }
  }
  return points;
}

function emaPoints(bars, period) {
  const values = closeValues(bars);
  return nullableValuesToPoints(bars, emaNullable(values, period));
}

function emaNullable(values, period) {
  const out = new Array(values.length).fill(null);
  if (values.length < period) return out;
  const multiplier = 2 / (period + 1);
  let seed = 0;
  for (let i = 0; i < period; i += 1) seed += values[i];
  let ema = seed / period;
  out[period - 1] = ema;
  for (let i = period; i < values.length; i += 1) {
    ema = values[i] * multiplier + ema * (1 - multiplier);
    out[i] = ema;
  }
  return out;
}

function emaFromNullable(values, period) {
  const out = new Array(values.length).fill(null);
  const multiplier = 2 / (period + 1);
  let seed = 0;
  let seeded = 0;
  let ema = null;
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (value === null || Number.isNaN(value)) continue;
    if (ema === null) {
      seed += value;
      seeded += 1;
      if (seeded === period) {
        ema = seed / period;
        out[i] = ema;
      }
      continue;
    }
    ema = value * multiplier + ema * (1 - multiplier);
    out[i] = ema;
  }
  return out;
}

function bollingerPoints(bars, period, deviations) {
  const values = closeValues(bars);
  const middle = [];
  const upper = [];
  const lower = [];
  for (let i = period - 1; i < values.length; i += 1) {
    const window = values.slice(i - period + 1, i + 1);
    const mean = window.reduce((sum, value) => sum + value, 0) / period;
    const variance = window.reduce((sum, value) => sum + (value - mean) ** 2, 0) / period;
    const band = Math.sqrt(variance) * deviations;
    middle.push({ time: bars[i].time, value: roundValue(mean) });
    upper.push({ time: bars[i].time, value: roundValue(mean + band) });
    lower.push({ time: bars[i].time, value: roundValue(mean - band) });
  }
  return { middle, upper, lower };
}

function macdPoints(bars, fastPeriod, slowPeriod, signalPeriod) {
  const values = closeValues(bars);
  const fast = emaNullable(values, fastPeriod);
  const slow = emaNullable(values, slowPeriod);
  const macdValues = values.map((_value, index) => {
    if (fast[index] === null || slow[index] === null) return null;
    return fast[index] - slow[index];
  });
  const signalValues = emaFromNullable(macdValues, signalPeriod);
  const macd = [];
  const signal = [];
  const histogram = [];
  for (let i = 0; i < bars.length; i += 1) {
    if (macdValues[i] !== null) {
      macd.push({ time: bars[i].time, value: roundValue(macdValues[i]) });
    }
    if (signalValues[i] !== null) {
      signal.push({ time: bars[i].time, value: roundValue(signalValues[i]) });
      const value = macdValues[i] - signalValues[i];
      histogram.push({
        time: bars[i].time,
        value: roundValue(value),
        color: value >= 0 ? "rgba(15, 139, 95, 0.55)" : "rgba(201, 76, 76, 0.55)",
      });
    }
  }
  return { macd, signal, histogram };
}

function rsiPoints(bars, period) {
  const values = closeValues(bars);
  if (values.length <= period) return [];
  const points = [];
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i += 1) {
    const change = values[i] - values[i - 1];
    if (change >= 0) gain += change;
    else loss -= change;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  points.push({ time: bars[period].time, value: rsiValue(avgGain, avgLoss) });
  for (let i = period + 1; i < values.length; i += 1) {
    const change = values[i] - values[i - 1];
    const currentGain = Math.max(change, 0);
    const currentLoss = Math.max(-change, 0);
    avgGain = (avgGain * (period - 1) + currentGain) / period;
    avgLoss = (avgLoss * (period - 1) + currentLoss) / period;
    points.push({ time: bars[i].time, value: rsiValue(avgGain, avgLoss) });
  }
  return points;
}

function rsiValue(avgGain, avgLoss) {
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return roundValue(100 - 100 / (1 + rs));
}

function horizontalLinePoints(bars, value) {
  if (!bars.length) return [];
  return [
    { time: bars[0].time, value },
    { time: bars[bars.length - 1].time, value },
  ];
}

function nullableValuesToPoints(bars, values) {
  const points = [];
  for (let i = 0; i < values.length; i += 1) {
    if (values[i] === null || Number.isNaN(values[i])) continue;
    points.push({ time: bars[i].time, value: roundValue(values[i]) });
  }
  return points;
}

function nullableArrayFromPoints(bars, points) {
  const byTime = new Map(points.map((point) => [point.time, point.value]));
  return bars.map((bar) => byTime.get(bar.time) ?? null);
}

function bollingerArrays(bars, period, deviations) {
  const values = closeValues(bars);
  const middle = new Array(bars.length).fill(null);
  const upper = new Array(bars.length).fill(null);
  const lower = new Array(bars.length).fill(null);
  for (let i = period - 1; i < values.length; i += 1) {
    const window = values.slice(i - period + 1, i + 1);
    const mean = window.reduce((sum, value) => sum + value, 0) / period;
    const variance = window.reduce((sum, value) => sum + (value - mean) ** 2, 0) / period;
    const band = Math.sqrt(variance) * deviations;
    middle[i] = mean;
    upper[i] = mean + band;
    lower[i] = mean - band;
  }
  return { middle, upper, lower };
}

function roundValue(value) {
  return Math.round(value * 1000000) / 1000000;
}

function formatPercent(value) {
  if (value === null || !Number.isFinite(value)) return "--";
  return `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value, digits = 2) {
  if (value === null || !Number.isFinite(value)) return "--";
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatCurrency(value) {
  if (value === null || !Number.isFinite(value)) return "--";
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function syncStrategyFields() {
  const isDualMa = els.strategy.value === "dual_ma";
  els.bollingerModeField.hidden = isDualMa;
  for (const node of document.querySelectorAll(".ma-param")) {
    node.hidden = !isDualMa;
  }
  for (const node of document.querySelectorAll(".boll-param")) {
    node.hidden = isDualMa;
  }
}

function showEmpty(message) {
  els.emptyState.textContent = message;
  els.emptyState.hidden = false;
  try {
    if (state.candleSeries) state.candleSeries.setData([]);
    if (state.volumeSeries) state.volumeSeries.setData([]);
    if (state.candleSeries) state.candleSeries.setMarkers([]);
    clearPriceIndicators();
  } catch (_error) {
    // Keep the visible error message even if the chart library rejects clearing.
  }
  els.macdPanel.hidden = true;
  els.rsiPanel.hidden = true;
  els.activeSymbol.textContent = "--";
  els.coverageRange.textContent = "--";
  els.visibleRange.textContent = "--";
  els.barCount.textContent = "--";
}

function setLoading(isLoading) {
  els.load.disabled = isLoading;
  els.load.querySelector("span:last-child").textContent = isLoading ? "加载中" : "加载";
}

function debounce(fn, delay = 220) {
  let timer = 0;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

async function bootstrap() {
  if (!window.LightweightCharts) {
    showEmpty("Lightweight Charts CDN 未加载，请检查网络连接");
    return;
  }

  applyIndicatorQuery();
  syncStrategyFields();
  initCharts();
  await loadMeta();
  await loadSymbols({ pickFirst: true });
  await loadBars();
}

function applyIndicatorQuery() {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("indicators");
  if (!value) return;
  const requested = value === "all" ? els.indicators.map((input) => input.dataset.indicator) : value.split(",");
  const requestedSet = new Set(requested.map((item) => item.trim().toLowerCase()).filter(Boolean));
  for (const input of els.indicators) {
    input.checked = requestedSet.has(input.dataset.indicator);
  }
}

const reloadSymbolsAndBars = async () => {
  await loadSymbols({ pickFirst: true });
  await loadBars();
};

els.market.addEventListener("change", reloadSymbolsAndBars);
els.adjustment.addEventListener("change", reloadSymbolsAndBars);
els.symbol.addEventListener("input", debounce(() => loadSymbols()));
els.symbol.addEventListener("change", () => {
  syncSelectedSymbolBounds();
  loadBars();
});
els.startDate.addEventListener("change", loadBars);
els.endDate.addEventListener("change", loadBars);
els.load.addEventListener("click", loadBars);
els.backtestButton.addEventListener("click", runBacktest);
els.strategy.addEventListener("change", () => {
  syncStrategyFields();
  if (state.lastPayload) runBacktest();
});
for (const input of [
  els.bollingerMode,
  els.fastMa,
  els.slowMa,
  els.bollPeriod,
  els.bollDev,
  els.initialCapital,
  els.feeBps,
]) {
  input.addEventListener("change", () => {
    if (state.lastPayload) runBacktest();
  });
}
for (const input of els.indicators) {
  input.addEventListener("change", () => {
    if (state.lastPayload) renderBars(state.lastPayload, { fitContent: false });
  });
}

bootstrap().catch((error) => showEmpty(error.message));

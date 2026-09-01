const state = {
  meta: [],
  symbols: [],
  templates: [],
  priceChart: null,
  equityChart: null,
  candleSeries: null,
  volumeSeries: null,
  equitySeries: null,
  resizeObserver: null,
  lastResult: null,
  lastBacktestRequest: null,
  lastOptimization: null,
  lastStrategyTableMarkdown: "",
  backtestHistory: [],
  selectedHistoryId: null,
};

const els = {
  market: document.querySelector("#marketSelect"),
  adjustment: document.querySelector("#adjustmentSelect"),
  symbol: document.querySelector("#symbolInput"),
  symbolOptions: document.querySelector("#symbolOptions"),
  startDate: document.querySelector("#startDateInput"),
  endDate: document.querySelector("#endDateInput"),
  template: document.querySelector("#templateSelect"),
  entryExpression: document.querySelector("#entryExpressionInput"),
  exitExpression: document.querySelector("#exitExpressionInput"),
  initialCapital: document.querySelector("#initialCapitalInput"),
  feeBps: document.querySelector("#feeBpsInput"),
  targetPercent: document.querySelector("#targetPercentInput"),
  capacityParticipation: document.querySelector("#capacityParticipationInput"),
  monteCarloRuns: document.querySelector("#monteCarloRunsInput"),
  walkWindow: document.querySelector("#walkWindowInput"),
  walkStep: document.querySelector("#walkStepInput"),
  run: document.querySelector("#runButton"),
  objective: document.querySelector("#objectiveSelect"),
  xParam: document.querySelector("#xParamSelect"),
  yParam: document.querySelector("#yParamSelect"),
  maxCombos: document.querySelector("#maxCombosInput"),
  xRangeTitle: document.querySelector("#xRangeTitle"),
  yRangeTitle: document.querySelector("#yRangeTitle"),
  xMin: document.querySelector("#xMinInput"),
  xMax: document.querySelector("#xMaxInput"),
  xStep: document.querySelector("#xStepInput"),
  yMin: document.querySelector("#yMinInput"),
  yMax: document.querySelector("#yMaxInput"),
  yStep: document.querySelector("#yStepInput"),
  optimize: document.querySelector("#optimizeButton"),
  applyBest: document.querySelector("#applyBestButton"),
  optimizeStatus: document.querySelector("#optimizeStatus"),
  optimizationHeatmap: document.querySelector("#optimizationHeatmap"),
  optimizationTableBody: document.querySelector("#optimizationTableBody"),
  summary: document.querySelector("#datasetSummary"),
  activeSymbol: document.querySelector("#activeSymbol"),
  coverageRange: document.querySelector("#coverageRange"),
  visibleRange: document.querySelector("#visibleRange"),
  barCount: document.querySelector("#barCount"),
  priceChart: document.querySelector("#priceChart"),
  equityChart: document.querySelector("#equityChart"),
  priceEmpty: document.querySelector("#priceEmpty"),
  equityEmpty: document.querySelector("#equityEmpty"),
  finalEquity: document.querySelector("#finalEquity"),
  totalReturn: document.querySelector("#totalReturn"),
  annualReturn: document.querySelector("#annualReturn"),
  annualVolatility: document.querySelector("#annualVolatility"),
  sharpe: document.querySelector("#sharpe"),
  sortino: document.querySelector("#sortino"),
  calmar: document.querySelector("#calmar"),
  maxDrawdown: document.querySelector("#maxDrawdown"),
  winRate: document.querySelector("#winRate"),
  profitFactor: document.querySelector("#profitFactor"),
  tradeCount: document.querySelector("#tradeCount"),
  signalCount: document.querySelector("#signalCount"),
  turnover: document.querySelector("#turnover"),
  annualizedTurnover: document.querySelector("#annualizedTurnover"),
  totalFees: document.querySelector("#totalFees"),
  costDrag: document.querySelector("#costDrag"),
  capacity: document.querySelector("#capacity"),
  maxParticipation: document.querySelector("#maxParticipation"),
  p20TradedValue: document.querySelector("#p20TradedValue"),
  feeRateOnTraded: document.querySelector("#feeRateOnTraded"),
  monteCarloStatus: document.querySelector("#monteCarloStatus"),
  monteCarloChart: document.querySelector("#monteCarloChart"),
  monteCarloTableBody: document.querySelector("#monteCarloTableBody"),
  walkForwardStatus: document.querySelector("#walkForwardStatus"),
  walkForwardChart: document.querySelector("#walkForwardChart"),
  walkForwardTableBody: document.querySelector("#walkForwardTableBody"),
  copyStrategyTable: document.querySelector("#copyStrategyTableButton"),
  strategySummaryTableBody: document.querySelector("#strategySummaryTableBody"),
  tradeTableBody: document.querySelector("#tradeTableBody"),
  runStatus: document.querySelector("#runStatus"),
  llmPanel: document.querySelector("#llmPanel"),
  llmToggle: document.querySelector("#llmToggleButton"),
  llmStatus: document.querySelector("#llmStatus"),
  llmBaseUrl: document.querySelector("#llmBaseUrlInput"),
  llmModel: document.querySelector("#llmModelInput"),
  llmApiKey: document.querySelector("#llmApiKeyInput"),
  llmThinking: document.querySelector("#llmThinkingInput"),
  llmEvaluate: document.querySelector("#llmEvaluateButton"),
  historyClear: document.querySelector("#historyClearButton"),
  historyList: document.querySelector("#historyList"),
  llmOutput: document.querySelector("#llmOutput"),
};

const HISTORY_STORAGE_KEY = "quantsystem.backtest.history.v1";
const LLM_SETTINGS_KEY = "quantsystem.backtest.llm.settings.v1";
const LLM_API_KEY_SESSION_KEY = "quantsystem.backtest.llm.apiKey.session";

const marketLabels = {
  ashare: "A股 HS300",
  usstock: "美股 S&P 500",
};

const adjustmentLabels = {
  qfq: "前复权 / Adjusted",
  unadjusted: "不复权",
};

const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:10110" : "";

function qs(params) {
  return new URLSearchParams(params).toString();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(`${API_BASE}${url}`, options);
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
    rightPriceScale: { borderColor: "#d9e0ea" },
    timeScale: {
      borderColor: "#d9e0ea",
      timeVisible: false,
      secondsVisible: false,
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    width: container.clientWidth,
    height,
  };
}

function initCharts() {
  state.priceChart = LightweightCharts.createChart(els.priceChart, chartOptions(els.priceChart, els.priceChart.clientHeight));
  state.candleSeries = state.priceChart.addCandlestickSeries({
    upColor: "#0f8b5f",
    downColor: "#c94c4c",
    borderUpColor: "#0f8b5f",
    borderDownColor: "#c94c4c",
    wickUpColor: "#0f8b5f",
    wickDownColor: "#c94c4c",
  });
  state.volumeSeries = state.priceChart.addHistogramSeries({
    color: "rgba(104, 114, 130, 0.34)",
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
  });
  state.priceChart.priceScale("right").applyOptions({ scaleMargins: { top: 0.08, bottom: 0.28 } });
  state.priceChart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });

  state.equityChart = LightweightCharts.createChart(els.equityChart, chartOptions(els.equityChart, els.equityChart.clientHeight));
  state.equitySeries = state.equityChart.addLineSeries({
    title: "Equity",
    color: "#0f8b8d",
    lineWidth: 2,
    priceLineVisible: false,
  });

  state.resizeObserver = new ResizeObserver(resizeCharts);
  state.resizeObserver.observe(els.priceChart);
  state.resizeObserver.observe(els.equityChart);
}

function resizeCharts() {
  state.priceChart.applyOptions({ width: els.priceChart.clientWidth, height: els.priceChart.clientHeight });
  state.equityChart.applyOptions({ width: els.equityChart.clientWidth, height: els.equityChart.clientHeight });
}

async function loadMeta() {
  const payload = await fetchJson("/api/meta");
  state.meta = payload.summary;
  els.summary.textContent = state.meta
    .map((row) => `${marketLabels[row.market]} ${adjustmentLabels[row.adjustment]}: ${row.symbols} symbols, ${row.min_trade_date} to ${row.max_trade_date}`)
    .join(" | ");
}

async function loadTemplates() {
  const payload = await fetchJson("/api/templates");
  state.templates = payload.templates;
  els.template.replaceChildren(
    ...state.templates.map((template) => {
      const option = document.createElement("option");
      option.value = template.key;
      option.textContent = template.name;
      return option;
    })
  );
  if (state.templates.length) {
    applyTemplate(state.templates[0].key);
  }
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

function applyTemplate(key) {
  const template = state.templates.find((item) => item.key === key);
  if (!template) return;
  els.entryExpression.value = template.entry_expression;
  els.exitExpression.value = template.exit_expression;
  configureOptimizationForTemplate(template);
}

function configureOptimizationForTemplate(template) {
  const spec = template.optimization;
  state.lastOptimization = null;
  if (!spec) {
    els.optimize.disabled = true;
    els.applyBest.disabled = true;
    els.optimizeStatus.textContent = "当前模板不可优化";
    renderChartEmpty(els.optimizationHeatmap, "当前模板不可优化");
    els.optimizationTableBody.innerHTML = '<tr><td colspan="10">--</td></tr>';
    return;
  }
  els.optimize.disabled = false;
  els.applyBest.disabled = true;
  const params = Object.entries(spec.params);
  const options = params.map(([key, meta]) => {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = meta.label;
    return option;
  });
  els.xParam.replaceChildren(...options.map((option) => option.cloneNode(true)));
  els.yParam.replaceChildren(...options.map((option) => option.cloneNode(true)));
  els.xParam.value = spec.x_param;
  els.yParam.value = spec.y_param;
  applyRangeDefaults("x", spec.x_param);
  applyRangeDefaults("y", spec.y_param);
  els.optimizeStatus.textContent = "可搜索";
  renderChartEmpty(els.optimizationHeatmap, "等待搜索");
  els.optimizationTableBody.innerHTML = '<tr><td colspan="10">--</td></tr>';
}

function applyRangeDefaults(axis, paramName) {
  const spec = currentOptimizationSpec();
  const meta = spec?.params?.[paramName];
  if (!meta) return;
  const prefix = axis === "x" ? "x" : "y";
  els[`${prefix}RangeTitle`].textContent = `${axis === "x" ? "横轴" : "纵轴"}: ${meta.label}`;
  els[`${prefix}Min`].value = meta.min;
  els[`${prefix}Max`].value = meta.max;
  els[`${prefix}Step`].value = meta.step;
}

function currentTemplate() {
  return state.templates.find((item) => item.key === els.template.value);
}

function currentOptimizationSpec() {
  return currentTemplate()?.optimization;
}

function buildBacktestPayload(symbol) {
  return {
    market: els.market.value,
    adjustment: els.adjustment.value,
    symbol,
    start_date: els.startDate.value,
    end_date: els.endDate.value,
    entry_expression: els.entryExpression.value,
    exit_expression: els.exitExpression.value,
    initial_capital: readPositiveNumber(els.initialCapital, "初始资金"),
    fee_bps: readNumber(els.feeBps, "单边费率 bps", 0, 500),
    target_percent: readNumber(els.targetPercent, "目标仓位", 0.01, 1),
    capacity_participation: readNumber(els.capacityParticipation, "容量参与率", 0.01, 1),
    monte_carlo_runs: Math.floor(readNumber(els.monteCarloRuns, "蒙特卡洛次数", 0, 2000)),
    walk_forward_window: Math.floor(readNumber(els.walkWindow, "步进窗口", 30, 3000)),
    walk_forward_step: Math.floor(readNumber(els.walkStep, "步进步长", 1, 3000)),
  };
}

async function runBacktest({ recordHistory = true } = {}) {
  const symbol = els.symbol.value.trim().toUpperCase();
  if (!symbol) {
    showEmpty("请选择一个股票代码");
    return;
  }
  setLoading(true);
  let barsRendered = false;
  try {
    const barsPayload = await fetchJson(`/api/bars?${qs({
      market: els.market.value,
      adjustment: els.adjustment.value,
      symbol,
      start_date: els.startDate.value,
      end_date: els.endDate.value,
    })}`);
    renderBars(barsPayload);
    barsRendered = true;
    const requestPayload = buildBacktestPayload(symbol);
    state.lastBacktestRequest = requestPayload;
    const result = await fetchJson("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    renderBacktest(result);
    if (recordHistory) {
      recordBacktestHistory(requestPayload, result, barsPayload);
    }
  } catch (error) {
    if (barsRendered) {
      showBacktestError(error.message || String(error));
    } else {
      showEmpty(error.message || String(error));
    }
  } finally {
    setLoading(false);
  }
}

async function runOptimization() {
  const symbol = els.symbol.value.trim().toUpperCase();
  const spec = currentOptimizationSpec();
  if (!symbol || !spec) {
    showOptimizationError("请选择可优化模板和标的");
    return;
  }
  setOptimizing(true);
  try {
    const barsPayload = await fetchJson(`/api/bars?${qs({
      market: els.market.value,
      adjustment: els.adjustment.value,
      symbol,
      start_date: els.startDate.value,
      end_date: els.endDate.value,
    })}`);
    renderBars(barsPayload);
    const xParam = els.xParam.value;
    const yParam = els.yParam.value;
    if (xParam === yParam) throw new Error("横轴和纵轴参数不能相同");
    const payload = {
      market: els.market.value,
      adjustment: els.adjustment.value,
      symbol,
      start_date: els.startDate.value,
      end_date: els.endDate.value,
      template_key: els.template.value,
      x_param: xParam,
      y_param: yParam,
      ranges: {
        [xParam]: {
          min: readNumber(els.xMin, "横轴最小值", -100000, 100000),
          max: readNumber(els.xMax, "横轴最大值", -100000, 100000),
          step: readNumber(els.xStep, "横轴步长", 0.000001, 100000),
        },
        [yParam]: {
          min: readNumber(els.yMin, "纵轴最小值", -100000, 100000),
          max: readNumber(els.yMax, "纵轴最大值", -100000, 100000),
          step: readNumber(els.yStep, "纵轴步长", 0.000001, 100000),
        },
      },
      objective: els.objective.value,
      initial_capital: readPositiveNumber(els.initialCapital, "初始资金"),
      fee_bps: readNumber(els.feeBps, "单边费率 bps", 0, 500),
      target_percent: readNumber(els.targetPercent, "目标仓位", 0.01, 1),
      capacity_participation: readNumber(els.capacityParticipation, "容量参与率", 0.01, 1),
      max_combinations: Math.floor(readNumber(els.maxCombos, "最大组合数", 1, 2000)),
    };
    const result = await fetchJson("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderOptimization(result);
  } catch (error) {
    showOptimizationError(error.message || String(error));
  } finally {
    setOptimizing(false);
  }
}

function renderBars(payload) {
  if (!payload.bars.length) {
    showEmpty("这个日期区间没有可展示的K线");
    return;
  }
  els.priceEmpty.hidden = true;
  const candles = payload.bars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close }));
  const volumes = payload.bars.map((bar) => ({
    time: bar.time,
    value: bar.volume || 0,
    color: bar.close >= bar.open ? "rgba(15, 139, 95, 0.45)" : "rgba(201, 76, 76, 0.45)",
  }));
  state.candleSeries.setData(candles);
  state.volumeSeries.setData(volumes);
  state.candleSeries.setMarkers([]);
  state.priceChart.timeScale().fitContent();

  els.activeSymbol.textContent = `${payload.symbol} · ${marketLabels[payload.market]} · ${adjustmentLabels[payload.adjustment]}`;
  els.coverageRange.textContent = `${payload.coverage.min_trade_date} 至 ${payload.coverage.max_trade_date}`;
  els.visibleRange.textContent = `${payload.visible.start_date} 至 ${payload.visible.end_date}`;
  els.barCount.textContent = String(payload.visible.rows);
}

function renderBacktest(result) {
  state.lastResult = result;
  els.equityEmpty.hidden = true;
  state.equitySeries.setData(result.equity);
  state.equityChart.timeScale().fitContent();
  state.candleSeries.setMarkers(tradeMarkers(result.trades));
  renderMetrics(result.metrics, result.signals, result.liquidity);
  renderRobustness(result.robustness);
  renderStrategySummary(result);
  renderTradeTable(result.trades);
  els.runStatus.textContent = `${result.symbol} ${result.visible.start_date} 至 ${result.visible.end_date}`;
}

function recordBacktestHistory(requestPayload, result, barsPayload) {
  const metrics = result.metrics || {};
  const item = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    createdAt: new Date().toISOString(),
    templateName: currentTemplate()?.name || "自定义 DSL",
    request: JSON.parse(JSON.stringify(requestPayload)),
    result: JSON.parse(JSON.stringify(result)),
    bars: JSON.parse(JSON.stringify(barsPayload)),
    summary: {
      total_return: metrics.total_return,
      sharpe: metrics.sharpe,
      max_drawdown: metrics.max_drawdown,
      trade_count: metrics.trade_count,
    },
  };
  state.backtestHistory = [item, ...state.backtestHistory.filter((row) => row.id !== item.id)].slice(0, 30);
  state.selectedHistoryId = item.id;
  saveBacktestHistory();
  renderHistoryList();
}

function loadBacktestHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) || "[]");
    state.backtestHistory = Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    state.backtestHistory = [];
  }
  renderHistoryList();
}

function saveBacktestHistory() {
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(state.backtestHistory));
  } catch (_error) {
    state.backtestHistory = state.backtestHistory.slice(0, 10);
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(state.backtestHistory));
    } catch (_secondError) {
      els.llmStatus.textContent = "日志未能写入本地存储";
    }
  }
}

function renderHistoryList() {
  if (!state.backtestHistory.length) {
    els.historyList.innerHTML = '<div class="svg-empty">暂无回测日志</div>';
    return;
  }
  els.historyList.replaceChildren(
    ...state.backtestHistory.map((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `history-item${item.id === state.selectedHistoryId ? " is-active" : ""}`;
      button.title = "恢复并评价这次回测";
      const title = document.createElement("span");
      title.textContent = `${item.request.symbol} · ${item.templateName}`;
      const meta = document.createElement("small");
      meta.textContent = `${formatLocalTime(item.createdAt)} · 收益 ${formatPercent(item.summary?.total_return)} · Sharpe ${formatNumberOrDash(item.summary?.sharpe, 2)} · 回撤 ${formatPercent(item.summary?.max_drawdown)}`;
      button.append(title, meta);
      button.addEventListener("click", () => selectHistoryRun(item.id));
      return button;
    })
  );
}

function selectHistoryRun(id) {
  const item = state.backtestHistory.find((row) => row.id === id);
  if (!item) return;
  state.selectedHistoryId = id;
  applyBacktestRequestToControls(item.request);
  state.lastBacktestRequest = item.request;
  if (item.bars) renderBars(item.bars);
  renderBacktest(item.result);
  renderHistoryList();
  evaluateBacktestItem(item);
}

function applyBacktestRequestToControls(requestPayload) {
  els.market.value = requestPayload.market || els.market.value;
  els.adjustment.value = requestPayload.adjustment || els.adjustment.value;
  els.symbol.value = requestPayload.symbol || els.symbol.value;
  els.startDate.value = requestPayload.start_date || els.startDate.value;
  els.endDate.value = requestPayload.end_date || els.endDate.value;
  els.entryExpression.value = requestPayload.entry_expression || els.entryExpression.value;
  els.exitExpression.value = requestPayload.exit_expression || els.exitExpression.value;
  els.initialCapital.value = requestPayload.initial_capital ?? els.initialCapital.value;
  els.feeBps.value = requestPayload.fee_bps ?? els.feeBps.value;
  els.targetPercent.value = requestPayload.target_percent ?? els.targetPercent.value;
  els.capacityParticipation.value = requestPayload.capacity_participation ?? els.capacityParticipation.value;
  els.monteCarloRuns.value = requestPayload.monte_carlo_runs ?? els.monteCarloRuns.value;
  els.walkWindow.value = requestPayload.walk_forward_window ?? els.walkWindow.value;
  els.walkStep.value = requestPayload.walk_forward_step ?? els.walkStep.value;
}

function tradeMarkers(trades) {
  const markers = [];
  for (const trade of trades) {
    markers.push({
      time: trade.entryDate,
      position: "belowBar",
      color: "#0f8b5f",
      shape: "arrowUp",
      text: "BUY",
    });
    markers.push({
      time: trade.exitDate,
      position: "aboveBar",
      color: "#c94c4c",
      shape: "arrowDown",
      text: "SELL",
    });
  }
  return markers.sort((a, b) => a.time.localeCompare(b.time));
}

function renderMetrics(metrics, signals, liquidity) {
  els.finalEquity.textContent = formatCurrency(metrics.final_equity);
  els.totalReturn.textContent = formatPercent(metrics.total_return);
  els.annualReturn.textContent = formatPercent(metrics.annual_return);
  els.annualVolatility.textContent = formatPercent(metrics.annual_volatility);
  els.sharpe.textContent = formatNumberOrDash(metrics.sharpe, 2);
  els.sortino.textContent = formatNumberOrDash(metrics.sortino, 2);
  els.calmar.textContent = formatNumberOrDash(metrics.calmar, 2);
  els.maxDrawdown.textContent = formatPercent(metrics.max_drawdown);
  els.winRate.textContent = formatPercent(metrics.win_rate);
  els.profitFactor.textContent = formatNumberOrDash(metrics.profit_factor, 2);
  els.tradeCount.textContent = String(metrics.trade_count || 0);
  els.signalCount.textContent = `${signals.entry_count || 0} / ${signals.exit_count || 0}`;
  els.turnover.textContent = formatNumberOrDash(metrics.turnover, 2);
  els.annualizedTurnover.textContent = formatNumberOrDash(metrics.annualized_turnover, 2);
  els.totalFees.textContent = formatCurrency(metrics.total_fees);
  els.costDrag.textContent = formatPercent(metrics.cost_drag);
  els.capacity.textContent = formatCurrency(liquidity?.capacity_at_participation);
  els.maxParticipation.textContent = formatPercent(metrics.max_fill_participation);
  els.p20TradedValue.textContent = formatCurrency(liquidity?.p20_daily_traded_value);
  els.feeRateOnTraded.textContent = formatNumberOrDash(metrics.fee_rate_on_traded_value_bps, 2);
}

function renderRobustness(robustness) {
  renderMonteCarlo(robustness?.monte_carlo);
  renderWalkForward(robustness?.walk_forward);
}

function renderMonteCarlo(mc) {
  if (!mc || !mc.enabled) {
    els.monteCarloStatus.textContent = mc?.reason || "--";
    renderChartEmpty(els.monteCarloChart, mc?.reason || "暂无蒙特卡洛数据");
    els.monteCarloTableBody.innerHTML = '<tr><td colspan="5">--</td></tr>';
    return;
  }
  els.monteCarloStatus.textContent = `${mc.runs} paths`;
  renderHistogramChart(els.monteCarloChart, mc.max_drawdown_histogram || [], {
    color: "#27364a",
    valueFormatter: formatPercent,
  });
  const rows = [
    ["终值收益", formatPercent(mc.terminal_return.p05), formatPercent(mc.terminal_return.p50), formatPercent(mc.terminal_return.p95), formatPercent(mc.terminal_return.min)],
    ["最大回撤", formatPercent(mc.max_drawdown.p05), formatPercent(mc.max_drawdown.p50), formatPercent(mc.max_drawdown.p95), formatPercent(mc.max_drawdown.max)],
    ["Sharpe", formatNumberOrDash(mc.sharpe.p05, 2), formatNumberOrDash(mc.sharpe.p50, 2), formatNumberOrDash(mc.sharpe.p95, 2), formatNumberOrDash(mc.sharpe.min, 2)],
  ];
  els.monteCarloTableBody.replaceChildren(...rows.map(miniTableRow));
}

function renderWalkForward(walk) {
  if (!walk || !walk.enabled) {
    els.walkForwardStatus.textContent = walk?.reason || "--";
    renderChartEmpty(els.walkForwardChart, walk?.reason || "暂无步进窗口数据");
    els.walkForwardTableBody.innerHTML = '<tr><td colspan="5">--</td></tr>';
    return;
  }
  const summary = walk.summary || {};
  const warmupText = walk.warmup_bars ? ` · warmup ${walk.warmup_bars}` : "";
  els.walkForwardStatus.textContent = `${summary.window_count || 0} windows${warmupText} · 正收益 ${formatPercent(summary.positive_window_rate)}`;
  renderWalkForwardChart(els.walkForwardChart, walk.windows || []);
  const rows = walk.windows.map((row) => {
    if (!row.ok) {
      return [`${row.start_date}~${row.end_date}`, "失败", row.error || "--", "--", "--"];
    }
    return [
      `${row.start_date}~${row.end_date}`,
      formatPercent(row.total_return),
      formatNumberOrDash(row.sharpe, 2),
      formatPercent(row.max_drawdown),
      formatNumberOrDash(row.turnover, 2),
    ];
  });
  els.walkForwardTableBody.replaceChildren(...rows.map(miniTableRow));
}

function renderOptimization(result) {
  state.lastOptimization = result;
  els.applyBest.disabled = !result.best;
  const objectiveLabel = els.objective.options[els.objective.selectedIndex]?.textContent || result.objective;
  els.optimizeStatus.textContent = `${result.valid_combinations}/${result.total_combinations} 有效 · ${objectiveLabel}`;
  renderOptimizationHeatmap(result);
  renderOptimizationTable(result);
}

async function applyBestOptimization() {
  const best = state.lastOptimization?.best;
  if (!best) return;
  els.entryExpression.value = best.entry_expression;
  els.exitExpression.value = best.exit_expression;
  els.optimizeStatus.textContent = `已应用最佳: ${formatParams(best.params, state.lastOptimization.param_labels)}`;
  await runBacktest();
}

function renderOptimizationTable(result) {
  const rows = result.top || [];
  if (!rows.length) {
    els.optimizationTableBody.innerHTML = '<tr><td colspan="10">无有效参数组合</td></tr>';
    return;
  }
  els.optimizationTableBody.replaceChildren(
    ...rows.map((row, idx) => {
      const metrics = row.metrics || {};
      return miniTableRow([
        String(idx + 1),
        formatParams(row.params, result.param_labels),
        formatObjective(row.score, result.objective),
        formatPercent(metrics.total_return),
        formatNumberOrDash(metrics.sharpe, 2),
        formatNumberOrDash(metrics.calmar, 2),
        formatPercent(metrics.max_drawdown),
        formatNumberOrDash(metrics.turnover, 2),
        `${formatCurrency(metrics.total_fees)} / ${formatPercent(metrics.cost_drag)}`,
        String(metrics.trade_count || 0),
      ]);
    })
  );
}

function renderOptimizationHeatmap(result) {
  const heatmap = result.heatmap;
  if (!heatmap || !heatmap.cells?.length) {
    renderChartEmpty(els.optimizationHeatmap, "暂无优化结果");
    return;
  }
  const values = heatmap.cells.flat().map((cell) => Number(cell.value)).filter(Number.isFinite);
  if (!values.length) {
    renderChartEmpty(els.optimizationHeatmap, "无有效参数组合");
    return;
  }
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const width = 760;
  const height = 318;
  const pad = { top: 18, right: 94, bottom: 50, left: 72 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const cols = heatmap.x_values.length;
  const rows = heatmap.y_values.length;
  const cellW = plotW / cols;
  const cellH = plotH / rows;
  const bestParams = result.best?.params || {};
  const cells = heatmap.cells
    .map((row, rowIdx) =>
      row
        .map((cell, colIdx) => {
          const value = Number(cell.value);
          const ok = cell.ok && Number.isFinite(value);
          const x = pad.left + colIdx * cellW;
          const y = pad.top + rowIdx * cellH;
          const fill = ok ? heatColor(value, minValue, maxValue, result.objective) : "#edf2f7";
          const isBest = result.best && cell.x === bestParams[result.x_param] && cell.y === bestParams[result.y_param];
          const stroke = isBest ? "#17202a" : "#ffffff";
          const strokeWidth = isBest ? 2.5 : 1;
          const title = ok
            ? `${result.param_labels[result.x_param]}=${cell.x}, ${result.param_labels[result.y_param]}=${cell.y}, ${result.objective}=${formatObjective(value, result.objective)}`
            : `${cell.x}, ${cell.y}: 无效`;
          return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(1, cellW - 1).toFixed(2)}" height="${Math.max(1, cellH - 1).toFixed(2)}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}"><title>${escapeSvg(title)}</title></rect>`;
        })
        .join("")
    )
    .join("");
  const xLabels = heatmap.x_values
    .map((value, idx) => {
      if (idx % Math.ceil(cols / 8) !== 0 && idx !== cols - 1) return "";
      const x = pad.left + idx * cellW + cellW / 2;
      return `<text x="${x.toFixed(2)}" y="${height - 24}" text-anchor="middle" fill="#667386" font-size="10">${escapeSvg(value)}</text>`;
    })
    .join("");
  const yLabels = heatmap.y_values
    .map((value, idx) => {
      if (idx % Math.ceil(rows / 8) !== 0 && idx !== rows - 1) return "";
      const y = pad.top + idx * cellH + cellH / 2 + 3;
      return `<text x="${pad.left - 8}" y="${y.toFixed(2)}" text-anchor="end" fill="#667386" font-size="10">${escapeSvg(value)}</text>`;
    })
    .join("");
  const legend = heatLegend(minValue, maxValue, result.objective, pad.left + plotW + 24, pad.top, plotH);
  containerSetSvg(
    els.optimizationHeatmap,
    `
    <svg viewBox="0 0 ${width} ${height}" role="img">
      ${cells}
      ${xLabels}
      ${yLabels}
      ${legend}
      <text x="${pad.left + plotW / 2}" y="${height - 8}" text-anchor="middle" fill="#667386" font-size="11">${escapeSvg(result.param_labels[result.x_param])}</text>
      <text x="14" y="${pad.top + plotH / 2}" transform="rotate(-90 14 ${pad.top + plotH / 2})" text-anchor="middle" fill="#667386" font-size="11">${escapeSvg(result.param_labels[result.y_param])}</text>
    </svg>
  `
  );
}

function containerSetSvg(container, markup) {
  container.innerHTML = markup;
}

function heatColor(value, minValue, maxValue, objective) {
  if (minValue === maxValue) return "#8fd3c7";
  let t = (value - minValue) / (maxValue - minValue);
  if (objective === "max_drawdown") t = 1 - t;
  t = Math.max(0, Math.min(1, t));
  const low = [201, 76, 76];
  const mid = [245, 247, 251];
  const high = [15, 139, 95];
  const from = t < 0.5 ? low : mid;
  const to = t < 0.5 ? mid : high;
  const local = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  const rgb = from.map((channel, idx) => Math.round(channel + (to[idx] - channel) * local));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

function heatLegend(minValue, maxValue, objective, x, y, h) {
  const id = `heatLegend${objective}`;
  return `
    <defs>
      <linearGradient id="${id}" x1="0" x2="0" y1="1" y2="0">
        <stop offset="0%" stop-color="#c94c4c" />
        <stop offset="50%" stop-color="#f5f7fb" />
        <stop offset="100%" stop-color="#0f8b5f" />
      </linearGradient>
    </defs>
    <rect x="${x}" y="${y}" width="14" height="${h}" fill="url(#${id})" stroke="#d9e1ec" />
    <text x="${x + 22}" y="${y + 10}" fill="#667386" font-size="10">${escapeSvg(formatObjective(objective === "max_drawdown" ? minValue : maxValue, objective))}</text>
    <text x="${x + 22}" y="${y + h}" fill="#667386" font-size="10">${escapeSvg(formatObjective(objective === "max_drawdown" ? maxValue : minValue, objective))}</text>
  `;
}

function renderHistogramChart(container, bins, { color, valueFormatter, baseline = null }) {
  const cleanBins = bins.filter((bin) => Number.isFinite(Number(bin.mid)) && Number.isFinite(Number(bin.count)));
  if (!cleanBins.length) {
    renderChartEmpty(container, "暂无分布数据");
    return;
  }
  const width = 720;
  const height = 190;
  const pad = { top: 12, right: 16, bottom: 34, left: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const maxCount = Math.max(...cleanBins.map((bin) => Number(bin.count)), 1);
  const minValue = Math.min(...cleanBins.map((bin) => Number(bin.start)));
  const maxValue = Math.max(...cleanBins.map((bin) => Number(bin.end)));
  const barGap = 3;
  const barW = Math.max(2, plotW / cleanBins.length - barGap);
  const bars = cleanBins
    .map((bin, idx) => {
      const count = Number(bin.count);
      const x = pad.left + idx * (plotW / cleanBins.length) + barGap / 2;
      const h = (count / maxCount) * plotH;
      const y = pad.top + plotH - h;
      const label = `${valueFormatter(bin.start)} ~ ${valueFormatter(bin.end)}: ${count}`;
      return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barW.toFixed(2)}" height="${h.toFixed(2)}" rx="2" fill="${color}"><title>${escapeSvg(label)}</title></rect>`;
    })
    .join("");
  const baselineX =
    baseline !== null && minValue < baseline && maxValue > baseline
      ? pad.left + ((baseline - minValue) / (maxValue - minValue)) * plotW
      : null;
  const baselineLine =
    baselineX === null
      ? ""
      : `<line x1="${baselineX.toFixed(2)}" y1="${pad.top}" x2="${baselineX.toFixed(2)}" y2="${pad.top + plotH}" stroke="#c94c4c" stroke-width="1" stroke-dasharray="4 4" />`;
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img">
      <line x1="${pad.left}" y1="${pad.top + plotH}" x2="${pad.left + plotW}" y2="${pad.top + plotH}" stroke="#d9e1ec" />
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${pad.top + plotH}" stroke="#d9e1ec" />
      ${baselineLine}
      ${bars}
      <text x="${pad.left}" y="${height - 10}" fill="#667386" font-size="11">${escapeSvg(valueFormatter(minValue))}</text>
      <text x="${pad.left + plotW}" y="${height - 10}" text-anchor="end" fill="#667386" font-size="11">${escapeSvg(valueFormatter(maxValue))}</text>
      <text x="${pad.left - 8}" y="${pad.top + 10}" text-anchor="end" fill="#667386" font-size="11">${maxCount}</text>
    </svg>
  `;
}

function renderWalkForwardChart(container, windows) {
  const rows = windows.filter((row) => row.ok && Number.isFinite(Number(row.total_return)) && Number.isFinite(Number(row.max_drawdown)));
  if (!rows.length) {
    renderChartEmpty(container, "暂无有效窗口");
    return;
  }
  const width = 720;
  const height = 190;
  const pad = { top: 12, right: 16, bottom: 42, left: 46 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const returns = rows.map((row) => Number(row.total_return));
  const drawdowns = rows.map((row) => -Number(row.max_drawdown));
  const minY = Math.min(0, ...returns, ...drawdowns);
  const maxY = Math.max(0, ...returns, ...drawdowns);
  const spanY = maxY - minY || 1;
  const xStep = plotW / rows.length;
  const barW = Math.max(8, xStep * 0.58);
  const zeroY = pad.top + ((maxY - 0) / spanY) * plotH;
  const yFor = (value) => pad.top + ((maxY - value) / spanY) * plotH;
  const xFor = (idx) => pad.left + idx * xStep + xStep / 2;
  const bars = rows
    .map((row, idx) => {
      const value = Number(row.total_return);
      const x = xFor(idx) - barW / 2;
      const y = yFor(Math.max(value, 0));
      const h = Math.max(1, Math.abs(yFor(value) - zeroY));
      const fill = value >= 0 ? "#0f8b5f" : "#c94c4c";
      const label = `${row.start_date}~${row.end_date} 收益 ${formatPercent(value)}`;
      return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barW.toFixed(2)}" height="${h.toFixed(2)}" rx="2" fill="${fill}" opacity="0.78"><title>${escapeSvg(label)}</title></rect>`;
    })
    .join("");
  const points = drawdowns.map((value, idx) => `${xFor(idx).toFixed(2)},${yFor(value).toFixed(2)}`).join(" ");
  const labels = rows
    .map((row, idx) => {
      if (idx % Math.ceil(rows.length / 4) !== 0 && idx !== rows.length - 1) return "";
      return `<text x="${xFor(idx).toFixed(2)}" y="${height - 12}" text-anchor="middle" fill="#667386" font-size="10">${escapeSvg(row.start_date.slice(2, 7))}</text>`;
    })
    .join("");
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img">
      <line x1="${pad.left}" y1="${zeroY.toFixed(2)}" x2="${pad.left + plotW}" y2="${zeroY.toFixed(2)}" stroke="#d9e1ec" />
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${pad.top + plotH}" stroke="#d9e1ec" />
      ${bars}
      <polyline points="${points}" fill="none" stroke="#27364a" stroke-width="2" />
      <text x="${pad.left - 8}" y="${yFor(maxY).toFixed(2)}" text-anchor="end" fill="#667386" font-size="11">${escapeSvg(formatPercent(maxY))}</text>
      <text x="${pad.left - 8}" y="${yFor(minY).toFixed(2)}" text-anchor="end" fill="#667386" font-size="11">${escapeSvg(formatPercent(minY))}</text>
      <text x="${pad.left + plotW - 2}" y="${pad.top + 12}" text-anchor="end" fill="#0f8b5f" font-size="11">收益柱</text>
      <text x="${pad.left + plotW - 2}" y="${pad.top + 28}" text-anchor="end" fill="#27364a" font-size="11">回撤线</text>
      ${labels}
    </svg>
  `;
}

function renderChartEmpty(container, message) {
  container.innerHTML = `<div class="svg-empty">${escapeHtml(message)}</div>`;
}

function escapeSvg(value) {
  return String(value ?? "--")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeHtml(value) {
  return escapeSvg(value);
}

function miniTableRow(cells) {
  const row = document.createElement("tr");
  for (const cell of cells) {
    const td = document.createElement("td");
    td.textContent = cell;
    row.appendChild(td);
  }
  return row;
}

function renderStrategySummary(result) {
  const metrics = result.metrics || {};
  const liquidity = result.liquidity || {};
  const walkSummary = result.robustness?.walk_forward?.summary || {};
  const mcDrawdown = result.robustness?.monte_carlo?.max_drawdown || {};
  const rows = [
    ["市场", `${marketLabels[result.market]} · ${adjustmentLabels[result.adjustment]}`],
    ["标的", result.symbol],
    ["区间", `${result.visible.start_date} 至 ${result.visible.end_date} · ${result.visible.rows} bars`],
    ["入场 DSL", result.entry_expression],
    ["出场 DSL", result.exit_expression],
    ["初始资金", formatCurrency(result.initial_capital)],
    ["目标仓位", formatPercent(result.target_percent)],
    ["单边费率", `${formatNumberOrDash(result.fee_bps, 2)} bps`],
    ["总收益 / 年化", `${formatPercent(metrics.total_return)} / ${formatPercent(metrics.annual_return)}`],
    ["Sharpe / Calmar", `${formatNumberOrDash(metrics.sharpe, 2)} / ${formatNumberOrDash(metrics.calmar, 2)}`],
    ["最大回撤", formatPercent(metrics.max_drawdown)],
    ["胜率 / 盈亏比", `${formatPercent(metrics.win_rate)} / ${formatNumberOrDash(metrics.profit_factor, 2)}`],
    ["交易次数 / 信号", `${metrics.trade_count || 0} / ${result.signals.entry_count || 0}-${result.signals.exit_count || 0}`],
    ["总换手 / 年化换手", `${formatNumberOrDash(metrics.turnover, 2)} / ${formatNumberOrDash(metrics.annualized_turnover, 2)}`],
    ["交易成本 / 拖累", `${formatCurrency(metrics.total_fees)} / ${formatPercent(metrics.cost_drag)}`],
    ["容量估计", `${formatCurrency(liquidity.capacity_at_participation)} @ ${formatPercent(liquidity.capacity_participation)} ADV(P20)`],
    ["最大成交占比", formatPercent(metrics.max_fill_participation)],
    ["蒙特卡洛最坏回撤", formatPercent(mcDrawdown.max)],
    ["步进窗口正收益率", formatPercent(walkSummary.positive_window_rate)],
    ["步进窗口最差收益", formatPercent(walkSummary.worst_total_return)],
  ];
  els.strategySummaryTableBody.replaceChildren(...rows.map((cells) => miniTableRow(cells)));
  state.lastStrategyTableMarkdown = markdownTable(rows);
}

function markdownTable(rows) {
  const escaped = rows.map(([key, value]) => [escapeTableCell(key), escapeTableCell(value)]);
  return ["| 字段 | 值 |", "| :--- | :--- |", ...escaped.map(([key, value]) => `| ${key} | ${value} |`)].join("\n");
}

function escapeTableCell(value) {
  return String(value ?? "--").replace(/\|/g, "\\|").replace(/\n/g, " ");
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
        trade.entrySignalDate || "--",
        trade.entryDate,
        trade.exitDate,
        formatNumber(trade.entryPrice, 3),
        formatNumber(trade.exitPrice, 3),
        formatNumber(trade.shares, 2),
        formatCurrency(trade.grossPnl),
        formatCurrency(trade.fee),
        formatCurrency(trade.netPnl),
        formatPercent(trade.returnPct),
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

async function loadLlmStatus() {
  loadLlmSettings();
  try {
    const status = await fetchJson("/api/llm/status");
    state.llmDefaults = status;
    if (!localStorage.getItem(LLM_SETTINGS_KEY)) {
      els.llmBaseUrl.value = status.base_url || "https://api.deepseek.com/v1";
      els.llmModel.value = status.chat_model || "deepseek-v4-flash";
    }
    els.llmStatus.textContent = status.configured ? "服务端 Key 已配置" : "可输入临时 Key";
  } catch (error) {
    els.llmStatus.textContent = error.message || String(error);
  }
}

function loadLlmSettings() {
  try {
    const settings = JSON.parse(localStorage.getItem(LLM_SETTINGS_KEY) || "{}");
    if (settings.base_url) els.llmBaseUrl.value = settings.base_url;
    if (settings.model) els.llmModel.value = settings.model;
    els.llmThinking.checked = Boolean(settings.thinking_mode);
  } catch (_error) {
    // Ignore malformed local settings.
  }
  els.llmApiKey.value = sessionStorage.getItem(LLM_API_KEY_SESSION_KEY) || "";
}

function saveLlmSettings() {
  localStorage.setItem(
    LLM_SETTINGS_KEY,
    JSON.stringify({
      base_url: els.llmBaseUrl.value.trim(),
      model: els.llmModel.value.trim(),
      thinking_mode: els.llmThinking.checked,
    })
  );
  if (els.llmApiKey.value.trim()) {
    sessionStorage.setItem(LLM_API_KEY_SESSION_KEY, els.llmApiKey.value.trim());
  } else {
    sessionStorage.removeItem(LLM_API_KEY_SESSION_KEY);
  }
}

async function evaluateCurrentBacktest() {
  if (state.selectedHistoryId) {
    const selected = state.backtestHistory.find((item) => item.id === state.selectedHistoryId);
    if (selected) {
      await evaluateBacktestItem(selected);
      return;
    }
  }
  if (!state.lastResult || !state.lastBacktestRequest) {
    renderMarkdown("**暂无可评价的回测。**\n\n先运行一次回测，或从回测日志里选择一条记录。");
    return;
  }
  await evaluateBacktestItem({
    id: "current",
    request: state.lastBacktestRequest,
    result: state.lastResult,
  });
}

async function evaluateBacktestItem(item) {
  saveLlmSettings();
  setLlmLoading(true);
  renderMarkdown("正在请求 DeepSeek 评价这次回测...");
  try {
    const response = await fetchJson("/api/llm/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_request: item.request,
        result: item.result,
        thinking_mode: els.llmThinking.checked,
        api_key: els.llmApiKey.value.trim() || null,
        base_url: els.llmBaseUrl.value.trim() || null,
        model: els.llmModel.value.trim() || null,
      }),
    });
    renderMarkdown(response.markdown);
    els.llmStatus.textContent = `${response.model} 已评价`;
  } catch (error) {
    renderMarkdown(`**LLM 评价失败**\n\n${error.message || String(error)}\n\n可在浮窗输入 DeepSeek API Key，或在启动服务前设置 \`DEEPSEEK_API_KEY\`。`);
    els.llmStatus.textContent = "评价失败";
  } finally {
    setLlmLoading(false);
  }
}

function setLlmLoading(isLoading) {
  els.llmEvaluate.disabled = isLoading;
  els.llmEvaluate.querySelector("span:last-child").textContent = isLoading ? "评价中" : "评价当前";
}

function toggleLlmPanel() {
  els.llmPanel.classList.toggle("is-collapsed");
}

function clearBacktestHistory() {
  state.backtestHistory = [];
  state.selectedHistoryId = null;
  localStorage.removeItem(HISTORY_STORAGE_KEY);
  renderHistoryList();
  renderMarkdown("回测日志已清空。");
}

function handleThinkingModeChange() {
  const defaults = state.llmDefaults || {};
  const current = els.llmModel.value.trim();
  if (els.llmThinking.checked && (!current || current === defaults.chat_model || current === "deepseek-chat" || current === "deepseek-v4-flash")) {
    els.llmModel.value = defaults.reasoner_model || "deepseek-reasoner";
  } else if (!els.llmThinking.checked && (!current || current === defaults.reasoner_model || current === "deepseek-reasoner")) {
    els.llmModel.value = defaults.chat_model || "deepseek-v4-flash";
  }
  saveLlmSettings();
}

function renderMarkdown(markdown) {
  els.llmOutput.innerHTML = markdownToHtml(markdown);
}

function markdownToHtml(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let list = null;
  let inCode = false;
  let codeLines = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (!list) return;
    html.push(`</${list}>`);
    list = null;
  };

  for (let idx = 0; idx < lines.length; idx += 1) {
    const line = lines[idx];
    if (line.trim().startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        flushParagraph();
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      closeList();
      continue;
    }
    if (isMarkdownTableStart(lines, idx)) {
      flushParagraph();
      closeList();
      const table = collectMarkdownTable(lines, idx);
      html.push(table.html);
      idx = table.endIndex;
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const unordered = /^\s*[-*]\s+(.+)$/.exec(line);
    if (unordered) {
      flushParagraph();
      if (list !== "ul") {
        closeList();
        list = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
      continue;
    }
    const ordered = /^\s*\d+\.\s+(.+)$/.exec(line);
    if (ordered) {
      flushParagraph();
      if (list !== "ol") {
        closeList();
        list = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
      continue;
    }
    paragraph.push(line.trim());
  }
  flushParagraph();
  closeList();
  if (inCode) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  return html.join("");
}

function isMarkdownTableStart(lines, idx) {
  return /^\s*\|.+\|\s*$/.test(lines[idx] || "") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[idx + 1] || "");
}

function collectMarkdownTable(lines, startIndex) {
  const tableLines = [];
  let idx = startIndex;
  while (idx < lines.length && /^\s*\|.+\|\s*$/.test(lines[idx])) {
    tableLines.push(lines[idx]);
    idx += 1;
  }
  const rows = tableLines
    .filter((_line, rowIdx) => rowIdx !== 1)
    .map((line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim()));
  const head = rows[0] || [];
  const body = rows.slice(1);
  const thead = `<thead><tr>${head.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  return { html: `<table>${thead}${tbody}</table>`, endIndex: idx - 1 };
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function showEmpty(message) {
  els.priceEmpty.textContent = message;
  els.equityEmpty.textContent = message;
  els.priceEmpty.hidden = false;
  els.equityEmpty.hidden = false;
  state.candleSeries.setData([]);
  state.volumeSeries.setData([]);
  state.candleSeries.setMarkers([]);
  state.equitySeries.setData([]);
  state.lastResult = null;
  state.lastBacktestRequest = null;
  state.lastStrategyTableMarkdown = "";
  resetMetrics();
  els.monteCarloStatus.textContent = "--";
  els.walkForwardStatus.textContent = "--";
  renderChartEmpty(els.monteCarloChart, "--");
  renderChartEmpty(els.walkForwardChart, "--");
  els.monteCarloTableBody.innerHTML = '<tr><td colspan="5">--</td></tr>';
  els.walkForwardTableBody.innerHTML = '<tr><td colspan="5">--</td></tr>';
  els.strategySummaryTableBody.innerHTML = '<tr><td colspan="2">--</td></tr>';
  els.tradeTableBody.innerHTML = '<tr><td colspan="12">--</td></tr>';
  els.runStatus.textContent = message;
}

function showBacktestError(message) {
  els.equityEmpty.textContent = message;
  els.equityEmpty.hidden = false;
  state.equitySeries.setData([]);
  state.candleSeries.setMarkers([]);
  state.lastResult = null;
  state.lastBacktestRequest = null;
  state.lastStrategyTableMarkdown = "";
  resetMetrics();
  els.monteCarloStatus.textContent = message;
  els.walkForwardStatus.textContent = "--";
  renderChartEmpty(els.monteCarloChart, message);
  renderChartEmpty(els.walkForwardChart, "--");
  els.monteCarloTableBody.innerHTML = '<tr><td colspan="5">--</td></tr>';
  els.walkForwardTableBody.innerHTML = '<tr><td colspan="5">--</td></tr>';
  els.strategySummaryTableBody.innerHTML = '<tr><td colspan="2">--</td></tr>';
  els.tradeTableBody.innerHTML = '<tr><td colspan="12">--</td></tr>';
  els.runStatus.textContent = message;
}

function showOptimizationError(message) {
  state.lastOptimization = null;
  els.applyBest.disabled = true;
  els.optimizeStatus.textContent = message;
  renderChartEmpty(els.optimizationHeatmap, message);
  els.optimizationTableBody.innerHTML = '<tr><td colspan="10">--</td></tr>';
}

function resetMetrics() {
  for (const el of [
    els.finalEquity,
    els.totalReturn,
    els.annualReturn,
    els.annualVolatility,
    els.sharpe,
    els.sortino,
    els.calmar,
    els.maxDrawdown,
    els.winRate,
    els.profitFactor,
    els.tradeCount,
    els.signalCount,
    els.turnover,
    els.annualizedTurnover,
    els.totalFees,
    els.costDrag,
    els.capacity,
    els.maxParticipation,
    els.p20TradedValue,
    els.feeRateOnTraded,
  ]) {
    el.textContent = "--";
  }
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

function setLoading(isLoading) {
  els.run.disabled = isLoading;
  els.run.querySelector("span:last-child").textContent = isLoading ? "运行中" : "运行回测";
}

function setOptimizing(isOptimizing) {
  els.optimize.disabled = isOptimizing;
  els.applyBest.disabled = isOptimizing || !state.lastOptimization?.best;
  els.optimize.querySelector("span:last-child").textContent = isOptimizing ? "搜索中" : "搜索参数";
  if (isOptimizing) {
    els.optimizeStatus.textContent = "正在搜索参数组合";
  }
}

function formatPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatNumberOrDash(value, digits = 2) {
  if (value === "Infinity") return "∞";
  return formatNumber(value, digits);
}

function formatCurrency(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

function formatObjective(value, objective) {
  if (["annual_return", "total_return", "max_drawdown"].includes(objective)) {
    return formatPercent(value);
  }
  return formatNumberOrDash(value, 3);
}

function formatParams(params, labels = {}) {
  return Object.entries(params || {})
    .map(([key, value]) => `${labels[key] || key}=${formatParamValue(value)}`)
    .join(", ");
}

function formatParamValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value ?? "--");
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function formatLocalTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

const debouncedLoadSymbols = debounce(() => loadSymbols(), 220);

els.market.addEventListener("change", async () => {
  els.symbol.value = "";
  await loadSymbols({ pickFirst: true });
});
els.adjustment.addEventListener("change", async () => {
  await loadSymbols({ pickFirst: true });
});
els.symbol.addEventListener("input", debouncedLoadSymbols);
els.symbol.addEventListener("change", () => {
  const selected = state.symbols.find((item) => item.symbol === els.symbol.value.trim().toUpperCase());
  if (selected) applySymbolBounds(selected);
});
els.template.addEventListener("change", () => applyTemplate(els.template.value));
els.run.addEventListener("click", runBacktest);
els.optimize.addEventListener("click", runOptimization);
els.applyBest.addEventListener("click", applyBestOptimization);
els.xParam.addEventListener("change", () => applyRangeDefaults("x", els.xParam.value));
els.yParam.addEventListener("change", () => applyRangeDefaults("y", els.yParam.value));
els.copyStrategyTable.addEventListener("click", copyStrategyTable);
els.llmToggle.addEventListener("click", toggleLlmPanel);
els.llmEvaluate.addEventListener("click", evaluateCurrentBacktest);
els.historyClear.addEventListener("click", clearBacktestHistory);
els.llmThinking.addEventListener("change", handleThinkingModeChange);
els.llmBaseUrl.addEventListener("change", saveLlmSettings);
els.llmModel.addEventListener("change", saveLlmSettings);
els.llmApiKey.addEventListener("change", saveLlmSettings);

async function copyStrategyTable() {
  if (!state.lastStrategyTableMarkdown) return;
  try {
    await navigator.clipboard.writeText(state.lastStrategyTableMarkdown);
  } catch (_error) {
    const textarea = document.createElement("textarea");
    textarea.value = state.lastStrategyTableMarkdown;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  const label = els.copyStrategyTable.querySelector("span:last-child");
  label.textContent = "已复制";
  window.setTimeout(() => {
    label.textContent = "复制表格";
  }, 1200);
}

async function bootstrap() {
  initCharts();
  loadBacktestHistory();
  await loadLlmStatus();
  try {
    await Promise.all([loadMeta(), loadTemplates()]);
    await loadSymbols({ pickFirst: true });
    await runBacktest();
  } catch (error) {
    showEmpty(error.message || String(error));
  }
}

bootstrap();

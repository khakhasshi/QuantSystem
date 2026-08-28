import { FootprintAggregator } from "./footprint.js";

const START_TIME = Date.now();
const RECONNECT_BASE_MS = 1200;
const RECONNECT_MAX_MS = 15_000;
const TRADE_STALE_MS = 10_000;

const state = {
  connectionId: 0,
  reconnectAttempt: 0,
  reconnectTimer: null,
  socket: null,
  latestTrade: null,
  aggregator: new FootprintAggregator({
    startTime: START_TIME,
    intervalMs: 30_000,
    maxBuckets: 24,
    targetRows: 28
  })
};

const elements = {
  status: document.getElementById("status"),
  startedAt: document.getElementById("startedAt"),
  lastPrice: document.getElementById("lastPrice"),
  lastTradeTime: document.getElementById("lastTradeTime"),
  countdown: document.getElementById("countdown"),
  windowRange: document.getElementById("windowRange"),
  buyVolume: document.getElementById("buyVolume"),
  buyTrades: document.getElementById("buyTrades"),
  sellVolume: document.getElementById("sellVolume"),
  sellTrades: document.getElementById("sellTrades"),
  delta: document.getElementById("delta"),
  imbalance: document.getElementById("imbalance"),
  priceStep: document.getElementById("priceStep"),
  bucketCount: document.getElementById("bucketCount"),
  matrix: document.getElementById("footprintMatrix")
};

function connect() {
  const connectionId = state.connectionId + 1;
  state.connectionId = connectionId;
  setStatus("连接 Binance 逐笔", "connecting");

  const socket = new WebSocket("wss://stream.binance.com:9443/ws/btcusdt@trade");
  state.socket = socket;

  socket.addEventListener("open", () => {
    if (connectionId !== state.connectionId) {
      socket.close();
      return;
    }
    state.reconnectAttempt = 0;
    setStatus("Binance trade", "online");
  });

  socket.addEventListener("message", (message) => {
    if (connectionId !== state.connectionId) {
      return;
    }

    try {
      const trade = parseBinanceTrade(message);
      if (!trade) {
        return;
      }
      ingestTrade(trade);
    } catch (error) {
      console.warn("逐笔成交解析失败", error);
    }
  });

  socket.addEventListener("close", () => {
    if (connectionId === state.connectionId) {
      scheduleReconnect();
    }
  });

  socket.addEventListener("error", () => {
    setStatus("连接异常，重连中", "error");
    socket.close();
  });
}

function parseBinanceTrade(message) {
  const data = JSON.parse(message.data);
  const price = Number(data.p);
  const quantity = Number(data.q);
  const tradeTime = Number(data.T);
  if (!Number.isFinite(price) || !Number.isFinite(quantity)) {
    return null;
  }

  return {
    price,
    quantity,
    timestamp: Number.isFinite(tradeTime) ? tradeTime : Date.now(),
    side: data.m ? "sell" : "buy"
  };
}

function ingestTrade(trade) {
  const receivedAt = Date.now();
  state.latestTrade = {
    ...trade,
    receivedAt
  };
  state.aggregator.addTrade({
    ...trade,
    timestamp: receivedAt
  });
}

function scheduleReconnect() {
  if (state.reconnectTimer) {
    return;
  }

  state.reconnectAttempt += 1;
  const delay = Math.min(
    RECONNECT_BASE_MS * 2 ** Math.min(state.reconnectAttempt, 4),
    RECONNECT_MAX_MS
  );
  setStatus(`${Math.round(delay / 1000)}秒后重连`, "connecting");

  state.reconnectTimer = window.setTimeout(() => {
    state.reconnectTimer = null;
    connect();
  }, delay);
}

function render() {
  const now = Date.now();
  const snapshot = state.aggregator.getMatrix(now);
  renderHeader(now, snapshot);
  renderMatrix(snapshot);
}

function renderHeader(now, snapshot) {
  const latest = state.latestTrade;
  if (latest) {
    const isStale = now - latest.receivedAt > TRADE_STALE_MS;
    elements.lastPrice.textContent = formatPrice(latest.price);
    elements.lastTradeTime.textContent = `${latest.side === "buy" ? "主动买入" : "主动卖出"} ${formatQuantity(
      latest.quantity
    )} BTC / ${formatTime(latest.receivedAt)}`;

    if (isStale) {
      setStatus("逐笔成交延迟", "stale");
    } else if (elements.status.dataset.kind !== "online") {
      setStatus("Binance trade", "online");
    }
  }

  const current = snapshot.currentBucket;
  const totals = current?.totals ?? { buyVolume: 0, sellVolume: 0, buyTrades: 0, sellTrades: 0 };
  const delta = totals.buyVolume - totals.sellVolume;
  const totalVolume = totals.buyVolume + totals.sellVolume;
  const imbalancePct = totalVolume > 0 ? (delta / totalVolume) * 100 : 0;

  elements.countdown.textContent = `${Math.ceil(state.aggregator.getRemainingMs(now) / 1000)}s`;
  elements.windowRange.textContent = current ? `${formatTime(current.openTime)} - ${formatTime(current.closeTime)}` : "--";
  elements.buyVolume.textContent = `${formatQuantity(totals.buyVolume)} BTC`;
  elements.buyTrades.textContent = `${totals.buyTrades} 笔`;
  elements.sellVolume.textContent = `${formatQuantity(totals.sellVolume)} BTC`;
  elements.sellTrades.textContent = `${totals.sellTrades} 笔`;
  elements.delta.textContent = `${delta >= 0 ? "+" : ""}${formatQuantity(delta)} BTC`;
  elements.delta.className = delta >= 0 ? "positive" : "negative";
  elements.imbalance.textContent = `${imbalancePct >= 0 ? "+" : ""}${imbalancePct.toFixed(1)}%`;
  elements.priceStep.textContent = `$${snapshot.priceStep}`;
  elements.bucketCount.textContent = `${snapshot.buckets.length} / 24`;
}

function renderMatrix(snapshot) {
  const { buckets, levels, maxCellVolume } = snapshot;
  if (!buckets.length || !levels.length) {
    elements.matrix.innerHTML = '<div class="empty-state">等待逐笔成交流</div>';
    return;
  }

  const columns = ["116px", ...buckets.map(() => "minmax(132px, 1fr)")].join(" ");
  elements.matrix.style.setProperty("--matrix-columns", columns);

  const html = [
    '<div class="matrix-corner" role="columnheader">Price</div>',
    ...buckets.map((bucket) => `<div class="bucket-head" role="columnheader">${formatTime(bucket.openTime)}</div>`)
  ];

  for (const level of levels) {
    html.push(`<div class="price-level" role="rowheader">${formatPrice(level)}</div>`);
    for (const bucket of buckets) {
      const cell = bucket.levels.get(level) ?? emptyCell(level);
      html.push(renderCell(cell, maxCellVolume));
    }
  }

  elements.matrix.innerHTML = html.join("");
}

function renderCell(cell, maxCellVolume) {
  const sideTotal = cell.buyVolume + cell.sellVolume;
  const buyShare = sideTotal > 0 ? cell.buyVolume / sideTotal : 0.5;
  const sellShare = sideTotal > 0 ? cell.sellVolume / sideTotal : 0.5;
  const heat = maxCellVolume > 0 ? Math.min(1, sideTotal / maxCellVolume) : 0;
  const delta = cell.buyVolume - cell.sellVolume;
  const direction = delta > 0 ? "buy" : delta < 0 ? "sell" : "flat";

  return `
    <div class="footprint-cell ${direction}" role="cell" style="--heat:${heat.toFixed(3)}">
      <span class="cell-side sell" style="--share:${sellShare.toFixed(3)}">${formatCellVolume(cell.sellVolume)}</span>
      <span class="cell-side buy" style="--share:${buyShare.toFixed(3)}">${formatCellVolume(cell.buyVolume)}</span>
    </div>
  `;
}

function emptyCell(priceLevel) {
  return {
    priceLevel,
    buyVolume: 0,
    sellVolume: 0,
    buyTrades: 0,
    sellTrades: 0
  };
}

function setStatus(text, kind) {
  elements.status.textContent = text;
  elements.status.dataset.kind = kind;
}

function formatPrice(value) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

function formatQuantity(value) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  const absValue = Math.abs(value);
  const digits = absValue >= 10 ? 2 : absValue >= 1 ? 3 : 4;
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(value);
}

function formatCellVolume(value) {
  if (!Number.isFinite(value) || value <= 0) {
    return "";
  }
  return value >= 1 ? value.toFixed(2) : value.toFixed(3);
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(timestamp));
}

function boot() {
  elements.startedAt.textContent = `启动 ${formatTime(START_TIME)}`;
  connect();
  render();
  window.setInterval(render, 1000);
}

window.addEventListener("beforeunload", () => {
  state.connectionId += 1;
  if (state.reconnectTimer) {
    window.clearTimeout(state.reconnectTimer);
  }
  if (state.socket) {
    state.socket.close();
  }
});

boot();

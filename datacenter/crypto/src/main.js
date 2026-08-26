(function () {
  const MAX_POINTS = 90;
  const RECONNECT_BASE_MS = 1200;
  const RECONNECT_MAX_MS = 15000;

  const elements = {
    coinMark: document.getElementById("coinMark"),
    coinTabs: Array.from(document.querySelectorAll(".coin-tab")),
    pair: document.getElementById("pair"),
    price: document.getElementById("price"),
    status: document.getElementById("status"),
    changeRow: document.getElementById("changeRow"),
    changeAbs: document.getElementById("changeAbs"),
    changePct: document.getElementById("changePct"),
    high: document.getElementById("high"),
    low: document.getElementById("low"),
    volume: document.getElementById("volume"),
    updatedAt: document.getElementById("updatedAt"),
    canvas: document.getElementById("sparkline")
  };

  const assets = {
    BTC: {
      symbol: "BTC",
      name: "Bitcoin",
      binanceStream: "btcusdt",
      binancePair: "BTC/USDT",
      coinbaseProduct: "BTC-USD",
      coinbasePair: "BTC/USD"
    },
    ETH: {
      symbol: "ETH",
      name: "Ethereum",
      binanceStream: "ethusdt",
      binancePair: "ETH/USDT",
      coinbaseProduct: "ETH-USD",
      coinbasePair: "ETH/USD"
    },
    DOGE: {
      symbol: "DOGE",
      name: "Dogecoin",
      binanceStream: "dogeusdt",
      binancePair: "DOGE/USDT",
      coinbaseProduct: "DOGE-USD",
      coinbasePair: "DOGE/USD"
    },
    SOL: {
      symbol: "SOL",
      name: "Solana",
      binanceStream: "solusdt",
      binancePair: "SOL/USDT",
      coinbaseProduct: "SOL-USD",
      coinbasePair: "SOL/USD"
    }
  };

  const state = {
    activeSymbol: "BTC",
    activeFeedIndex: 0,
    connectionId: 0,
    reconnectAttempt: 0,
    reconnectTimer: null,
    socket: null,
    points: []
  };

  function buildFeeds(asset) {
    return [
      {
        name: `Binance ${asset.binancePair}`,
        pair: asset.binancePair,
        socketUrl: `wss://stream.binance.com:9443/ws/${asset.binanceStream}@ticker`,
        parse(message) {
          const data = JSON.parse(message.data);
          return {
            price: Number(data.c),
            changeAbs: Number(data.p),
            changePct: Number(data.P),
            high: Number(data.h),
            low: Number(data.l),
            volume: Number(data.v),
            updatedAt: Number(data.E)
          };
        }
      },
      {
        name: `Coinbase ${asset.coinbasePair}`,
        pair: asset.coinbasePair,
        socketUrl: "wss://ws-feed.exchange.coinbase.com",
        open(socket) {
          socket.send(
            JSON.stringify({
              type: "subscribe",
              product_ids: [asset.coinbaseProduct],
              channels: ["ticker"]
            })
          );
        },
        parse(message) {
          const data = JSON.parse(message.data);
          if (data.type !== "ticker" || data.product_id !== asset.coinbaseProduct) {
            return null;
          }

          const price = Number(data.price);
          const open = Number(data.open_24h);
          const changeAbs = Number.isFinite(open) ? price - open : NaN;
          const changePct = Number.isFinite(open) && open !== 0 ? (changeAbs / open) * 100 : NaN;

          return {
            price,
            changeAbs,
            changePct,
            high: Number(data.high_24h),
            low: Number(data.low_24h),
            volume: Number(data.volume_24h),
            updatedAt: Date.parse(data.time)
          };
        }
      }
    ];
  }

  function connect() {
    const connectionId = state.connectionId + 1;
    state.connectionId = connectionId;
    const asset = assets[state.activeSymbol];
    const feeds = buildFeeds(asset);
    const feed = feeds[state.activeFeedIndex];
    setStatus(`连接 ${feed.name}`, "connecting");

    const socket = new WebSocket(feed.socketUrl);
    state.socket = socket;

    socket.addEventListener("open", () => {
      if (connectionId !== state.connectionId) {
        socket.close();
        return;
      }

      state.reconnectAttempt = 0;
      setStatus(feed.name, "online");
      elements.pair.textContent = feed.pair;
      if (typeof feed.open === "function") {
        feed.open(socket);
      }
    });

    socket.addEventListener("message", (message) => {
      if (connectionId !== state.connectionId) {
        return;
      }

      try {
        const tick = feed.parse(message);
        if (!tick || !Number.isFinite(tick.price)) {
          return;
        }
        updateTick(tick);
      } catch (error) {
        console.warn("行情消息解析失败", error);
      }
    });

    socket.addEventListener("close", () => {
      if (connectionId === state.connectionId) {
        scheduleReconnect();
      }
    });
    socket.addEventListener("error", () => {
      setStatus("连接异常，切换中", "error");
      socket.close();
    });
  }

  function scheduleReconnect() {
    if (state.reconnectTimer) {
      return;
    }

    const feedCount = buildFeeds(assets[state.activeSymbol]).length;
    state.activeFeedIndex = (state.activeFeedIndex + 1) % feedCount;
    state.reconnectAttempt += 1;
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** Math.min(state.reconnectAttempt, 4),
      RECONNECT_MAX_MS
    );

    setStatus(`${Math.round(delay / 1000)} 秒后重连`, "connecting");
    state.reconnectTimer = window.setTimeout(() => {
      state.reconnectTimer = null;
      connect();
    }, delay);
  }

  function updateTick(tick) {
    const asset = assets[state.activeSymbol];
    const timestamp = Number.isFinite(tick.updatedAt) ? tick.updatedAt : Date.now();
    elements.price.textContent = formatPrice(tick.price);
    elements.high.textContent = formatCurrency(tick.high);
    elements.low.textContent = formatCurrency(tick.low);
    elements.volume.textContent = formatVolume(tick.volume, asset.symbol);
    elements.updatedAt.textContent = new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    }).format(new Date(timestamp));

    updateChange(tick.changeAbs, tick.changePct);
    addPoint(tick.price);
    drawSparkline();
  }

  function selectAsset(symbol) {
    if (!assets[symbol] || symbol === state.activeSymbol) {
      return;
    }

    clearReconnectTimer();
    state.connectionId += 1;
    if (state.socket) {
      state.socket.close();
      state.socket = null;
    }

    state.activeSymbol = symbol;
    state.activeFeedIndex = 0;
    state.reconnectAttempt = 0;
    state.points = [];
    resetDisplay();
    syncAssetChrome();
    drawSparkline();
    connect();
  }

  function clearReconnectTimer() {
    if (state.reconnectTimer) {
      window.clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
  }

  function resetDisplay() {
    elements.price.textContent = "--";
    elements.high.textContent = "--";
    elements.low.textContent = "--";
    elements.volume.textContent = "--";
    elements.updatedAt.textContent = "--";
    elements.changeRow.className = "change-row flat";
    elements.changeAbs.textContent = "--";
    elements.changePct.textContent = "--";
  }

  function syncAssetChrome() {
    const asset = assets[state.activeSymbol];
    elements.coinMark.textContent = asset.symbol;
    elements.pair.textContent = asset.binancePair;
    document.title = `${asset.symbol} 实时价格`;
    elements.coinTabs.forEach((button) => {
      const isActive = button.dataset.symbol === asset.symbol;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
  }

  function updateChange(changeAbs, changePct) {
    const hasAbs = Number.isFinite(changeAbs);
    const hasPct = Number.isFinite(changePct);
    const direction = hasAbs ? Math.sign(changeAbs) : 0;
    const className = direction > 0 ? "positive" : direction < 0 ? "negative" : "flat";

    elements.changeRow.className = `change-row ${className}`;
    elements.changeAbs.textContent = hasAbs ? `${direction >= 0 ? "+" : ""}${formatCurrency(changeAbs)}` : "--";
    elements.changePct.textContent = hasPct ? `${direction >= 0 ? "+" : ""}${changePct.toFixed(2)}%` : "--";
  }

  function addPoint(price) {
    state.points.push(price);
    if (state.points.length > MAX_POINTS) {
      state.points.shift();
    }
  }

  function drawSparkline() {
    const canvas = elements.canvas;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    const points = state.points;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#071017";
    ctx.fillRect(0, 0, width, height);

    drawGrid(ctx, width, height);
    if (points.length < 2) {
      return;
    }

    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = max - min || 1;
    const pad = 22;

    ctx.beginPath();
    points.forEach((point, index) => {
      const x = pad + (index / (MAX_POINTS - 1)) * (width - pad * 2);
      const y = height - pad - ((point - min) / range) * (height - pad * 2);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });

    const latest = points[points.length - 1];
    const first = points[0];
    const lineColor = latest >= first ? "#2ee59d" : "#ff5b7c";
    ctx.lineWidth = 5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.strokeStyle = lineColor;
    ctx.shadowColor = lineColor;
    ctx.shadowBlur = 18;
    ctx.stroke();
    ctx.shadowBlur = 0;

    const x = pad + ((points.length - 1) / (MAX_POINTS - 1)) * (width - pad * 2);
    const y = height - pad - ((latest - min) / range) * (height - pad * 2);
    ctx.fillStyle = lineColor;
    ctx.beginPath();
    ctx.arc(x, y, 7, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawGrid(ctx, width, height) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i += 1) {
      const y = (height / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
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

  function formatCurrency(value) {
    if (!Number.isFinite(value)) {
      return "--";
    }
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
  }

  function formatVolume(value, symbol) {
    if (!Number.isFinite(value)) {
      return "--";
    }
    return `${new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 2
    }).format(value)} ${symbol}`;
  }

  elements.coinTabs.forEach((button) => {
    button.addEventListener("click", () => selectAsset(button.dataset.symbol));
  });

  window.addEventListener("beforeunload", () => {
    state.connectionId += 1;
    clearReconnectTimer();
    if (state.socket) {
      state.socket.close();
    }
  });

  syncAssetChrome();
  connect();
})();

export const DEFAULT_INTERVAL_MS = 30_000;

export class CandleAggregator {
  constructor({ startTime = Date.now(), intervalMs = DEFAULT_INTERVAL_MS, maxCandles = 120 } = {}) {
    if (!Number.isFinite(startTime)) {
      throw new TypeError("startTime must be a finite timestamp");
    }
    if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
      throw new TypeError("intervalMs must be a positive number");
    }
    if (!Number.isInteger(maxCandles) || maxCandles <= 0) {
      throw new TypeError("maxCandles must be a positive integer");
    }

    this.startTime = startTime;
    this.intervalMs = intervalMs;
    this.maxCandles = maxCandles;
    this.candles = [];
  }

  addTick({ price, volume = 0, timestamp = Date.now() }) {
    if (!Number.isFinite(price) || price <= 0) {
      return null;
    }

    const bucketIndex = Math.max(0, Math.floor((timestamp - this.startTime) / this.intervalMs));
    const openTime = this.startTime + bucketIndex * this.intervalMs;
    const closeTime = openTime + this.intervalMs;
    let candle = this.candles[this.candles.length - 1];

    if (!candle || candle.bucketIndex !== bucketIndex) {
      candle = {
        bucketIndex,
        openTime,
        closeTime,
        open: price,
        high: price,
        low: price,
        close: price,
        volume: numberOrZero(volume),
        ticks: 1
      };
      this.candles.push(candle);
      if (this.candles.length > this.maxCandles) {
        this.candles.shift();
      }
      return candle;
    }

    candle.high = Math.max(candle.high, price);
    candle.low = Math.min(candle.low, price);
    candle.close = price;
    candle.volume += numberOrZero(volume);
    candle.ticks += 1;
    return candle;
  }

  getCandles() {
    return this.candles.map((candle) => ({ ...candle }));
  }

  getCurrentCandle() {
    const candle = this.candles[this.candles.length - 1];
    return candle ? { ...candle } : null;
  }

  getRemainingMs(now = Date.now()) {
    const elapsed = Math.max(0, now - this.startTime);
    const remainder = elapsed % this.intervalMs;
    return remainder === 0 && elapsed > 0 ? this.intervalMs : this.intervalMs - remainder;
  }
}

function numberOrZero(value) {
  return Number.isFinite(value) ? value : 0;
}

export class FootprintAggregator {
  constructor({ startTime = Date.now(), intervalMs = 30_000, maxBuckets = 24, targetRows = 28 } = {}) {
    if (!Number.isFinite(startTime)) {
      throw new TypeError("startTime must be a finite timestamp");
    }
    if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
      throw new TypeError("intervalMs must be a positive number");
    }
    if (!Number.isInteger(maxBuckets) || maxBuckets <= 0) {
      throw new TypeError("maxBuckets must be a positive integer");
    }
    if (!Number.isInteger(targetRows) || targetRows <= 0) {
      throw new TypeError("targetRows must be a positive integer");
    }

    this.startTime = startTime;
    this.intervalMs = intervalMs;
    this.maxBuckets = maxBuckets;
    this.targetRows = targetRows;
    this.rawTrades = [];
  }

  addTrade({ price, quantity, side, timestamp = Date.now() }) {
    if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(quantity) || quantity <= 0) {
      return null;
    }
    if (side !== "buy" && side !== "sell") {
      return null;
    }

    const bucketIndex = this.getBucketIndex(timestamp);
    const trade = {
      bucketIndex,
      price,
      quantity,
      side,
      timestamp
    };
    this.rawTrades.push(trade);
    this.trimTrades();
    return { ...trade };
  }

  getMatrix(now = Date.now()) {
    const visibleTrades = this.rawTrades.slice();
    const priceStep = choosePriceStep(visibleTrades, this.targetRows);
    const buckets = new Map();
    let minLevel = Infinity;
    let maxLevel = -Infinity;
    let maxCellVolume = 0;

    for (const trade of visibleTrades) {
      const bucket = getOrCreateBucket(buckets, trade.bucketIndex, this.startTime, this.intervalMs);
      const priceLevel = roundToStep(trade.price, priceStep);
      const cell = getOrCreateCell(bucket.levels, priceLevel);
      if (trade.side === "buy") {
        cell.buyVolume += trade.quantity;
        cell.buyTrades += 1;
        bucket.totals.buyVolume += trade.quantity;
        bucket.totals.buyTrades += 1;
      } else {
        cell.sellVolume += trade.quantity;
        cell.sellTrades += 1;
        bucket.totals.sellVolume += trade.quantity;
        bucket.totals.sellTrades += 1;
      }

      minLevel = Math.min(minLevel, priceLevel);
      maxLevel = Math.max(maxLevel, priceLevel);
      maxCellVolume = Math.max(maxCellVolume, cell.buyVolume + cell.sellVolume);
    }

    const sortedBuckets = Array.from(buckets.values()).sort((left, right) => left.bucketIndex - right.bucketIndex);
    const levels = Number.isFinite(minLevel) ? buildLevels(minLevel, maxLevel, priceStep, this.targetRows) : [];

    return {
      priceStep,
      buckets: sortedBuckets,
      levels,
      maxCellVolume,
      currentBucket: sortedBuckets.find((bucket) => bucket.bucketIndex === this.getBucketIndex(now)) ?? null
    };
  }

  getRemainingMs(now = Date.now()) {
    const elapsed = Math.max(0, now - this.startTime);
    const remainder = elapsed % this.intervalMs;
    return remainder === 0 && elapsed > 0 ? this.intervalMs : this.intervalMs - remainder;
  }

  getBucketIndex(timestamp) {
    return Math.max(0, Math.floor((timestamp - this.startTime) / this.intervalMs));
  }

  trimTrades() {
    const latest = this.rawTrades[this.rawTrades.length - 1];
    if (!latest) {
      return;
    }
    const minBucket = Math.max(0, latest.bucketIndex - this.maxBuckets + 1);
    this.rawTrades = this.rawTrades.filter((trade) => trade.bucketIndex >= minBucket);
  }
}

export function choosePriceStep(trades, targetRows = 28) {
  if (!trades.length) {
    return 1;
  }

  const prices = trades.map((trade) => trade.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const rawStep = Math.max(1, (max - min) / Math.max(1, targetRows - 1));
  const candidates = [1, 2, 5, 10, 20, 50, 100, 200, 500];
  return candidates.find((candidate) => candidate >= rawStep) ?? candidates[candidates.length - 1];
}

export function roundToStep(price, step) {
  return Math.round(price / step) * step;
}

function getOrCreateBucket(buckets, bucketIndex, startTime, intervalMs) {
  let bucket = buckets.get(bucketIndex);
  if (!bucket) {
    const openTime = startTime + bucketIndex * intervalMs;
    bucket = {
      bucketIndex,
      openTime,
      closeTime: openTime + intervalMs,
      levels: new Map(),
      totals: {
        buyVolume: 0,
        sellVolume: 0,
        buyTrades: 0,
        sellTrades: 0
      }
    };
    buckets.set(bucketIndex, bucket);
  }
  return bucket;
}

function getOrCreateCell(levels, priceLevel) {
  let cell = levels.get(priceLevel);
  if (!cell) {
    cell = {
      priceLevel,
      buyVolume: 0,
      sellVolume: 0,
      buyTrades: 0,
      sellTrades: 0
    };
    levels.set(priceLevel, cell);
  }
  return cell;
}

function buildLevels(minLevel, maxLevel, priceStep, targetRows) {
  const levels = [];
  const min = roundToStep(minLevel, priceStep);
  const max = roundToStep(maxLevel, priceStep);
  for (let level = max; level >= min; level -= priceStep) {
    levels.push(level);
  }

  if (levels.length >= targetRows) {
    return levels;
  }

  let nextTop = max + priceStep;
  let nextBottom = min - priceStep;
  while (levels.length < targetRows) {
    levels.unshift(nextTop);
    nextTop += priceStep;
    if (levels.length >= targetRows) {
      break;
    }
    levels.push(nextBottom);
    nextBottom -= priceStep;
  }
  return levels;
}

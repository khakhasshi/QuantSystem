import assert from "node:assert/strict";
import test from "node:test";

import { CandleAggregator } from "../src/candle.js";
import { FootprintAggregator, choosePriceStep, roundToStep } from "../src/footprint.js";

test("anchors 30-second buckets at system start time", () => {
  const candles = new CandleAggregator({ startTime: 1000, intervalMs: 30_000 });

  candles.addTick({ price: 100, volume: 1, timestamp: 1000 });
  candles.addTick({ price: 105, volume: 2, timestamp: 30_999 });
  candles.addTick({ price: 99, volume: 3, timestamp: 31_000 });

  const rows = candles.getCandles();
  assert.equal(rows.length, 2);
  assert.equal(rows[0].openTime, 1000);
  assert.equal(rows[0].closeTime, 31_000);
  assert.equal(rows[1].openTime, 31_000);
  assert.equal(rows[1].closeTime, 61_000);
});

test("updates OHLC, volume, and tick count inside the same candle", () => {
  const candles = new CandleAggregator({ startTime: 0, intervalMs: 30_000 });

  candles.addTick({ price: 10, volume: 1, timestamp: 100 });
  candles.addTick({ price: 12, volume: 1.5, timestamp: 500 });
  candles.addTick({ price: 9, volume: 2, timestamp: 900 });
  candles.addTick({ price: 11, volume: 0.5, timestamp: 1000 });

  assert.deepEqual(candles.getCurrentCandle(), {
    bucketIndex: 0,
    openTime: 0,
    closeTime: 30_000,
    open: 10,
    high: 12,
    low: 9,
    close: 11,
    volume: 5,
    ticks: 4
  });
});

test("caps retained candles", () => {
  const candles = new CandleAggregator({ startTime: 0, intervalMs: 30_000, maxCandles: 2 });

  candles.addTick({ price: 1, timestamp: 0 });
  candles.addTick({ price: 2, timestamp: 30_000 });
  candles.addTick({ price: 3, timestamp: 60_000 });

  assert.deepEqual(
    candles.getCandles().map((candle) => candle.open),
    [2, 3]
  );
});

test("reports remaining time in the active 30-second bucket", () => {
  const candles = new CandleAggregator({ startTime: 1000, intervalMs: 30_000 });

  assert.equal(candles.getRemainingMs(1000), 30_000);
  assert.equal(candles.getRemainingMs(10_999), 20_001);
  assert.equal(candles.getRemainingMs(31_000), 30_000);
});

test("footprint aggregates aggressive buy and sell trades by 30-second bucket", () => {
  const footprint = new FootprintAggregator({
    startTime: 1000,
    intervalMs: 30_000,
    maxBuckets: 4,
    targetRows: 8
  });

  footprint.addTrade({ price: 100.2, quantity: 0.3, side: "buy", timestamp: 1100 });
  footprint.addTrade({ price: 100.4, quantity: 0.2, side: "sell", timestamp: 1200 });
  footprint.addTrade({ price: 102.1, quantity: 0.5, side: "buy", timestamp: 31_000 });

  const matrix = footprint.getMatrix(31_100);
  assert.equal(matrix.buckets.length, 2);
  assert.equal(matrix.currentBucket.bucketIndex, 1);
  assert.equal(matrix.buckets[0].totals.buyVolume, 0.3);
  assert.equal(matrix.buckets[0].totals.sellVolume, 0.2);
  assert.equal(matrix.buckets[1].totals.buyTrades, 1);
});

test("footprint matrix keeps left sell and right buy values at the same price level", () => {
  const footprint = new FootprintAggregator({
    startTime: 0,
    intervalMs: 30_000,
    targetRows: 6
  });

  footprint.addTrade({ price: 79_300.1, quantity: 0.125, side: "sell", timestamp: 1 });
  footprint.addTrade({ price: 79_300.3, quantity: 0.375, side: "buy", timestamp: 2 });

  const matrix = footprint.getMatrix(10_000);
  const priceLevel = roundToStep(79_300.1, matrix.priceStep);
  const cell = matrix.buckets[0].levels.get(priceLevel);

  assert.equal(cell.sellVolume, 0.125);
  assert.equal(cell.buyVolume, 0.375);
  assert.equal(cell.sellTrades, 1);
  assert.equal(cell.buyTrades, 1);
});

test("footprint trims old buckets and adapts price step", () => {
  const footprint = new FootprintAggregator({ startTime: 0, intervalMs: 30_000, maxBuckets: 2 });

  footprint.addTrade({ price: 100, quantity: 1, side: "buy", timestamp: 1 });
  footprint.addTrade({ price: 110, quantity: 1, side: "buy", timestamp: 30_001 });
  footprint.addTrade({ price: 120, quantity: 1, side: "sell", timestamp: 60_001 });

  const matrix = footprint.getMatrix(60_001);
  assert.deepEqual(
    matrix.buckets.map((bucket) => bucket.bucketIndex),
    [1, 2]
  );
  assert.equal(choosePriceStep([{ price: 100 }, { price: 260 }], 20), 10);
});

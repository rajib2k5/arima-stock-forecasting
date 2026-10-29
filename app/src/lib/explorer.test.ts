import { describe, expect, it } from 'vitest'
import { decompositionXTicks, kdeMeta, kdePlot, nullEnds, orderedKdes, pricePlot, segmentBands, shortSha, signed, usd } from './explorer'
import { fixtureEda, fixturePrices } from '../test/fixtures/payloads'
import type { DecompositionRow } from './contract.payloads'

describe('pricePlot', () => {
  it('plots close_usd on the dollar axis and log_close on the log axis, straight from the rows', () => {
    const prices = fixturePrices()
    const dollars = pricePlot(prices, 'usd')
    const logs = pricePlot(prices, 'log')
    expect(dollars.series[0].ys).toEqual([24, 23.5, 23.5, 24, 25, 185])
    expect(logs.series[0].ys).toEqual([3.1781, 3.157, 3.157, 3.1781, 3.2189, 5.2204])
    expect(dollars.yLabel).toBe('adjusted close ($)')
    expect(logs.yLabel).toBe('log price, ln($)')
  })
  it('puts one x step on each trading day and a tick at the first day of each year', () => {
    const plot = pricePlot(fixturePrices(), 'usd')
    expect(plot.xs).toEqual([0, 1, 2, 3, 4, 5])
    expect(plot.xTicks).toEqual([
      { x: 0, label: '2015' },
      { x: 5, label: '2024' },
    ])
  })
  it('reads out the date, both prices and the segment of a row', () => {
    expect(pricePlot(fixturePrices(), 'log').readout(4)).toBe('2015-01-08 · $25.00 · ln 3.2189 · Test')
  })
})

describe('segmentBands', () => {
  it('makes one band per segment, labelled from the splits', () => {
    expect(segmentBands(fixturePrices())).toEqual([
      { from: 0, to: 3, kind: 'train', label: 'Train: 2015-01-02 to 2015-01-07, 4 trading days' },
      { from: 4, to: 4, kind: 'test', label: 'Test: 2015-01-08 to 2015-01-08, 1 trading day' },
      { from: 5, to: 5, kind: 'oos', label: 'Out of sample: 2024-01-02 to 2024-01-02, 1 trading day' },
    ])
  })
})

describe('KDE presentation', () => {
  it('names the two known variables and falls back to the raw name for others (open enum)', () => {
    expect(kdeMeta('log_return').title).toBe('Daily log return')
    expect(kdeMeta('log_close').xLabel).toBe('ln($)')
    expect(kdeMeta('close_usd')).toEqual({ title: 'close_usd', xLabel: 'close_usd', decimals: 4 })
  })
  it('draws the density and the normal reference from the points, without computing either', () => {
    const plot = kdePlot(fixtureEda().kdes[1])
    expect(plot.xs).toEqual([-0.06, 0, 0.06])
    expect(plot.series.map((s) => s.ys)).toEqual([
      [0.1, 18, 0.1],
      [0.05, 23, 0.05],
    ])
    expect(plot.series[1].dashed).toBe(true)
    expect(plot.readout(0)).toBe('x −0.0600 · density 0.1000 · normal 0.05000')
  })
  it('orders known variables first, then unknown ones', () => {
    const eda = fixtureEda()
    eda.kdes = [{ ...eda.kdes[0], variable: 'close_usd' }, eda.kdes[1], eda.kdes[0]]
    expect(orderedKdes(eda).map((k) => k.variable)).toEqual(['log_close', 'log_return', 'close_usd'])
  })
})

describe('decomposition presentation', () => {
  const row = (date: string, trend: number | null): DecompositionRow => ({ date, observed_log: 1, trend_log: trend, seasonal_log: 0, resid_log: trend === null ? null : 0 })
  it('counts the rows without a trend at each end', () => {
    expect(nullEnds(fixtureEda().decomposition.rows)).toEqual({ head: 1, tail: 1 })
    expect(nullEnds([row('2015-01-02', null), row('2015-01-05', null)])).toEqual({ head: 2, tail: 0 })
    expect(nullEnds([row('2015-01-02', 1)])).toEqual({ head: 0, tail: 0 })
  })
  it('labels the first row of each year', () => {
    expect(decompositionXTicks([row('2015-12-31', 1), row('2016-01-04', 1)])).toEqual([
      { x: 0, label: '2015' },
      { x: 1, label: '2016' },
    ])
  })
})

describe('formatting', () => {
  it('formats dollars, signed numbers and short hashes', () => {
    expect(usd(24.1717586517334)).toBe('$24.17')
    expect(signed(-0.224657, 3)).toBe('−0.225')
    expect(signed(-0.0001, 3)).toBe('0.000')
    expect(signed(5.2, 1)).toBe('5.2')
    expect(shortSha('0123456789abcdef'.repeat(4))).toBe('0123456789ab')
  })
})

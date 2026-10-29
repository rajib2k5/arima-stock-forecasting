import { describe, expect, it } from 'vitest'
import { extent, formatTick, gapPath, linearScale, nearestIndex, niceStep, niceTicks, runs, stepDecimals, yearTicks } from './plot'

describe('extent', () => {
  it('spans every series and skips nulls and non-finite values', () => {
    expect(extent([[3, null, 1], [NaN, 7, Infinity]])).toEqual([1, 7])
  })
  it('is null when nothing is finite', () => {
    expect(extent([[null, NaN]])).toBeNull()
    expect(extent([])).toBeNull()
  })
})

describe('linearScale', () => {
  it('maps the ends of the domain to the ends of the range, including a reversed range', () => {
    const s = linearScale([0, 10], [100, 0])
    expect([s(0), s(5), s(10)]).toEqual([100, 50, 0])
  })
  it('maps a zero-width domain to the middle of the range', () => {
    expect(linearScale([4, 4], [0, 10])(4)).toBe(5)
  })
})

describe('nice ticks', () => {
  it.each([
    [100, 5, 20],
    [3.2, 5, 0.5],
    [0.26, 4, 0.05],
    [1, 4, 0.2],
    [7000, 5, 1000],
  ])('niceStep(%d, %d) is %d', (range, target, step) => {
    expect(niceStep(range, target)).toBe(step)
  })
  it('falls back to 1 for an empty or invalid range', () => {
    expect(niceStep(0, 5)).toBe(1)
    expect(niceStep(5, 0)).toBe(1)
  })
  it('places ticks on multiples of the step inside the range, without float noise', () => {
    expect(niceTicks(0, 100, 5)).toEqual([0, 20, 40, 60, 80, 100])
    expect(niceTicks(2.5, 5.7, 5)).toEqual([2.5, 3, 3.5, 4, 4.5, 5, 5.5])
    expect(niceTicks(-0.13, 0.13, 4)).toEqual([-0.1, -0.05, 0, 0.05, 0.1])
    expect(niceTicks(0.1, 0.35, 5)).toEqual([0.1, 0.15, 0.2, 0.25, 0.3, 0.35])
  })
  it('returns the single value for an empty range and nothing for a non-finite one', () => {
    expect(niceTicks(3, 3)).toEqual([3])
    expect(niceTicks(NaN, 3)).toEqual([])
  })
  it('prints as many decimals as the step needs, with a real minus sign and no negative zero', () => {
    expect(stepDecimals(20)).toBe(0)
    expect(stepDecimals(0.5)).toBe(1)
    expect(stepDecimals(0.05)).toBe(2)
    expect(stepDecimals(0.1)).toBe(1)
    expect(formatTick(-0.05, 0.05)).toBe('−0.05')
    expect(formatTick(-0.0001, 0.05)).toBe('0.00')
    expect(formatTick(150, 50)).toBe('150')
  })
})

describe('runs', () => {
  it('groups consecutive equal values with inclusive ends', () => {
    expect(runs(['train', 'train', 'test', 'oos', 'oos'])).toEqual([
      { value: 'train', from: 0, to: 1 },
      { value: 'test', from: 2, to: 2 },
      { value: 'oos', from: 3, to: 4 },
    ])
    expect(runs([])).toEqual([])
  })
})

describe('yearTicks', () => {
  it('marks the first row of each calendar year', () => {
    expect(yearTicks(['2015-12-30', '2015-12-31', '2016-01-04', '2016-06-01', '2017-01-03'])).toEqual([
      { index: 0, label: '2015' },
      { index: 2, label: '2016' },
      { index: 4, label: '2017' },
    ])
  })
  it('keeps every k-th year when there are too many', () => {
    const dates = Array.from({ length: 12 }, (_, i) => `${2015 + i}-01-02`)
    expect(yearTicks(dates, 4).map((t) => t.label)).toEqual(['2015', '2018', '2021', '2024'])
  })
})

describe('nearestIndex', () => {
  const xs = [0, 1, 2, 10]
  it.each([
    [-5, 0],
    [0.4, 0],
    [0.5, 0],
    [0.6, 1],
    [6, 2],
    [6.1, 3],
    [99, 3],
  ])('x = %d is nearest to index %d', (x, i) => {
    expect(nearestIndex(xs, x)).toBe(i)
  })
  it('is -1 for no values and 0 for one', () => {
    expect(nearestIndex([], 3)).toBe(-1)
    expect(nearestIndex([7], 3)).toBe(0)
  })
})

describe('gapPath', () => {
  const id = (v: number) => v
  it('draws one sub-path per run of values and breaks at nulls', () => {
    expect(gapPath([0, 1, 2, 3, 4], [null, 5, 6, null, 8], id, id)).toBe('M1 5 L2 6 M4 8')
  })
  it('rounds coordinates to two decimals', () => {
    expect(gapPath([0, 1], [1 / 3, 2 / 3], id, (v) => v * 10)).toBe('M0 3.33 L1 6.67')
  })
  it('is empty when every value is missing', () => {
    expect(gapPath([0, 1], [null, NaN], id, id)).toBe('')
  })
})

import { describe, expect, it } from 'vitest'
import { drawingWidth, extent, formatLogTick, formatTick, gapPath, linearScale, logTicks, MIN_DRAWING_WIDTH, nearestIndex, niceStep, niceTicks, runs, stepDecimals, thinTicks, yearTicks } from './plot'

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

describe('logTicks', () => {
  it('takes the coarsest of 1, 2 and 5 times powers of ten, then finer steps, that gives three ticks', () => {
    expect(logTicks(1, 1e6)).toEqual([1, 10, 100, 1000, 10000, 100000, 1000000])
    expect(logTicks(15, 900)).toEqual([20, 50, 100, 200, 500])
    // The real static oos fan of the AIC model spans about $111 to $876.
    expect(logTicks(111, 876)).toEqual([150, 200, 300, 500, 700])
    expect(logTicks(150, 260)).toEqual([150, 200, 250])
    expect(logTicks(0.25, 0.9)).toEqual([0.3, 0.5, 0.7])
  })
  it('falls back to evenly spaced ticks on a range too narrow for any, and gives none for a range it cannot place', () => {
    expect(logTicks(33, 41)).toEqual(niceTicks(33, 41, 5))
    expect(logTicks(0, 10)).toEqual([])
    expect(logTicks(5, 2)).toEqual([])
    expect(logTicks(7, 7)).toEqual([7])
  })
  it('writes a tick with no trailing zeros', () => {
    expect([formatLogTick(150), formatLogTick(0.30000000000000004), formatLogTick(1500), formatLogTick(2.5)]).toEqual(['150', '0.3', '1500', '2.5'])
  })
})

describe('drawingWidth', () => {
  it('draws one unit per pixel in a container narrower than the drawing, so 10-unit text stays 10 px', () => {
    // A 375 px phone leaves a card 293 px wide.
    expect(drawingWidth(293, 720)).toBe(293)
    expect(drawingWidth(293.4, 420)).toBe(293)
    expect(drawingWidth(719, 720)).toBe(719)
  })
  it('keeps the nominal drawing in a container as wide or wider, and in one not measured yet', () => {
    expect(drawingWidth(720, 720)).toBe(720)
    expect(drawingWidth(1018, 720)).toBe(720)
    expect(drawingWidth(null, 720)).toBe(720)
    expect(drawingWidth(0, 720)).toBe(720)
    expect(drawingWidth(NaN, 420)).toBe(420)
  })
  it('never draws narrower than the minimum, nor wider than a drawing that is smaller than it', () => {
    expect(MIN_DRAWING_WIDTH).toBe(240)
    expect(drawingWidth(200, 720)).toBe(240)
    expect(drawingWidth(240, 720)).toBe(240)
    expect(drawingWidth(241, 720)).toBe(241)
    expect(drawingWidth(100, 200)).toBe(200)
    expect(drawingWidth(150, 720, 120)).toBe(150)
  })
})

describe('thinTicks', () => {
  const dates = ['2024-01-02', '2024-03-01', '2024-05-01', '2024-07-01', '2024-09-03'].map((label) => ({ label }))
  it('keeps every tick when the longest label fits between neighbours', () => {
    // Ten characters need 10 x 6.2 + 8 = 70 units: five dates on a 720-unit drawing are 162 apart.
    expect(thinTicks(dates, [58, 220, 382, 544, 706])).toEqual(dates)
    expect(thinTicks(dates, [0, 70, 140, 210, 280])).toEqual(dates)
  })
  it('keeps every k-th tick, the first always, when labels would run into each other', () => {
    // On a 293-unit drawing the five dates are 55 apart: every second one is kept.
    expect(thinTicks(dates, [58, 113, 168, 224, 279]).map((t) => t.label)).toEqual(['2024-01-02', '2024-05-01', '2024-09-03'])
    expect(thinTicks(dates, [0, 69.9, 139.8, 209.7, 279.6]).map((t) => t.label)).toEqual(['2024-01-02', '2024-05-01', '2024-09-03'])
    // Twelve years 18 units apart need 4 x 6.2 + 8 = 32.8 units each: every second year.
    const years = Array.from({ length: 12 }, (_, k) => ({ label: String(2015 + k) }))
    expect(thinTicks(years, years.map((_, k) => 58 + 18 * k)).map((t) => t.label)).toEqual(['2015', '2017', '2019', '2021', '2023', '2025'])
  })
  it('measures the tightest gap, and keeps only the first tick when two share a position', () => {
    // The tightest gap, 30 units, sets the step: ceil(70 / 30) = 3.
    expect(thinTicks(dates, [0, 200, 230, 430, 630]).map((t) => t.label)).toEqual(['2024-01-02', '2024-07-01'])
    expect(thinTicks(dates, [0, 0, 100, 200, 300]).map((t) => t.label)).toEqual(['2024-01-02'])
  })
  it('passes zero or one tick through', () => {
    expect(thinTicks([], [])).toEqual([])
    expect(thinTicks([{ label: 'x' }], [5])).toEqual([{ label: 'x' }])
  })
})

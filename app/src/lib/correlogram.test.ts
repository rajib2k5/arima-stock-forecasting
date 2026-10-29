import { describe, expect, it } from 'vitest'
import { bandPath, correlogramBars, correlogramDomain, lagTicks, readoutText } from './correlogram'
import type { CorrelogramSeries } from './contract.order'

const SERIES: CorrelogramSeries = {
  transform: 'diff1',
  d: 1,
  n: 400,
  acf_outside_count: 1,
  pacf_outside_count: 2,
  // The flags are Python's (|value| > band at lags >= 1), as the readers check them.
  rows: [
    { lag: 0, acf: 1, pacf: 1, acf_band: 0, pacf_band: 0, acf_outside: false, pacf_outside: false },
    { lag: 1, acf: -0.12, pacf: -0.12, acf_band: 0.098, pacf_band: 0.098, acf_outside: true, pacf_outside: true },
    { lag: 2, acf: 0.03, pacf: 0.15, acf_band: 0.1, pacf_band: 0.098, acf_outside: false, pacf_outside: true },
    { lag: 3, acf: 0.1, pacf: -0.01, acf_band: 0.1, pacf_band: 0.098, acf_outside: false, pacf_outside: false },
  ],
}

describe('correlogramBars', () => {
  it('leaves out lag 0 and carries the exported flag of each bar', () => {
    const bars = correlogramBars(SERIES, 'acf')
    expect(bars.map((b) => b.lag)).toEqual([1, 2, 3])
    // |-0.12| > 0.098: outside. 0.03 < 0.1: inside. 0.1 = 0.1: on the edge, not past it.
    expect(bars.map((b) => b.outside)).toEqual([true, false, false])
  })

  it('draws the flag Python exported, and never compares a value with its band itself', () => {
    // A row whose flag a comparison would contradict (the readers refuse such a file; this helper
    // must not second-guess it either way).
    const rows = SERIES.rows.map((row) => ({ ...row, acf_outside: !row.acf_outside, pacf_outside: !row.pacf_outside }))
    const flipped = { ...SERIES, rows }
    expect(correlogramBars(flipped, 'acf').map((b) => b.outside)).toEqual([false, true, true])
    expect(correlogramBars(flipped, 'pacf').map((b) => b.outside)).toEqual([false, false, true])
  })

  it('reads the PACF and its own band for the PACF', () => {
    const bars = correlogramBars(SERIES, 'pacf')
    expect(bars.map((b) => [b.value, b.band])).toEqual([
      [-0.12, 0.098],
      [0.15, 0.098],
      [-0.01, 0.098],
    ])
    expect(bars.map((b) => b.outside)).toEqual([true, true, false])
  })

  it('can include lag 0 when asked, which is never past its band', () => {
    expect(correlogramBars(SERIES, 'acf', 0)[0]).toEqual({ lag: 0, value: 1, band: 0, outside: false })
  })
})

describe('correlogramDomain', () => {
  it('is symmetric, holds the largest bar or band with 8% room, and is never narrower than 0.1', () => {
    expect(correlogramDomain(correlogramBars(SERIES, 'pacf'))).toEqual([-0.15 * 1.08, 0.15 * 1.08])
    expect(correlogramDomain([{ lag: 1, value: 0.01, band: 0.02, outside: false }])).toEqual([-0.1 * 1.08, 0.1 * 1.08])
  })
})

describe('bandPath', () => {
  it('steps along +band across each lag, then comes back along -band', () => {
    const bars = [
      { lag: 1, value: 0, band: 1, outside: false },
      { lag: 2, value: 0, band: 2, outside: false },
    ]
    const path = bandPath(bars, (lag) => lag * 10, (v) => -v, 5)
    expect(path).toBe('M5 -1 L15 -1 L15 -2 L25 -2 L25 2 L15 2 L15 1 L5 1 Z')
    expect(bandPath([], (x) => x, (y) => y, 1)).toBe('')
  })
})

describe('lagTicks and the readout', () => {
  it('ticks 1, then every tenth lag', () => {
    const bars = Array.from({ length: 50 }, (_, i) => ({ lag: i + 1, value: 0, band: 0.1, outside: false }))
    expect(lagTicks(bars)).toEqual([1, 10, 20, 30, 40, 50])
    expect(lagTicks(bars.slice(4))).toEqual([10, 20, 30, 40, 50])
    expect(lagTicks([])).toEqual([])
  })

  it('reads one lag with a real minus sign and says when the bar is past its band', () => {
    expect(readoutText('ACF', { lag: 7, value: -0.0871, band: 0.0446, outside: true })).toBe('lag 7 · ACF −0.0871 · band ±0.0446 · beyond the band')
    expect(readoutText('PACF', { lag: 2, value: 0.01, band: 0.0434, outside: false })).toBe('lag 2 · PACF 0.0100 · band ±0.0434')
  })
})

/**
 * Presentation helpers for the ACF and PACF bar charts (the course's plot_acf and plot_pacf).
 * Pure: they pick values from acf_pacf.json and map them to pixels. The bands are the exported
 * half-widths and the "past the band" flags are the exported ones; nothing here computes a
 * correlation, a band, or whether a bar is past it.
 */
import type { CorrelogramSeries } from './contract.order'

export type Correlation = 'acf' | 'pacf'

export interface CorrelogramBar {
  lag: number
  value: number
  /** Half-width of the 95% band around zero at this lag, as exported. */
  band: number
  /** The bar reaches past its band (drawn in the accent colour): Python's exported flag, not a comparison made here. */
  outside: boolean
}

/**
 * The bars from lag `fromLag` on. Lag 0 is left out by default: it is 1 by definition, and on a
 * scale that fits 1 the other lags of a return series would be invisible.
 */
export function correlogramBars(series: CorrelogramSeries, kind: Correlation, fromLag = 1): CorrelogramBar[] {
  return series.rows
    .filter((row) => row.lag >= fromLag)
    .map((row) => {
      const value = kind === 'acf' ? row.acf : row.pacf
      const band = kind === 'acf' ? row.acf_band : row.pacf_band
      return { lag: row.lag, value, band, outside: kind === 'acf' ? row.acf_outside : row.pacf_outside }
    })
}

/**
 * A y range symmetric around zero that holds every bar and every band, with a little room, and
 * never narrower than +-0.1 (so a near-zero chart still shows the band at a readable size).
 */
export function correlogramDomain(bars: readonly CorrelogramBar[]): [number, number] {
  const reach = Math.max(0.1, ...bars.map((b) => Math.max(Math.abs(b.value), b.band)))
  const top = reach * 1.08
  return [-top, top]
}

/**
 * The shaded band as one closed SVG path: the upper edge steps across each lag's width at +band,
 * the lower edge comes back at -band. `half` is half the distance between two lags, in pixels.
 */
export function bandPath(bars: readonly CorrelogramBar[], sx: (lag: number) => number, sy: (v: number) => number, half: number): string {
  if (bars.length === 0) return ''
  const r = (v: number) => Math.round(v * 100) / 100
  const upper = bars.flatMap((b) => [`${r(sx(b.lag) - half)} ${r(sy(b.band))}`, `${r(sx(b.lag) + half)} ${r(sy(b.band))}`])
  const lower = [...bars].reverse().flatMap((b) => [`${r(sx(b.lag) + half)} ${r(sy(-b.band))}`, `${r(sx(b.lag) - half)} ${r(sy(-b.band))}`])
  return `M${upper.join(' L')} L${lower.join(' L')} Z`
}

/** Lag ticks: every `step` lags, starting at the first multiple of `step` (and 1 when it is shown). */
export function lagTicks(bars: readonly CorrelogramBar[], step = 10): number[] {
  if (bars.length === 0) return []
  const first = bars[0].lag
  const last = bars[bars.length - 1].lag
  const ticks = first === 1 ? [1] : []
  for (let lag = Math.ceil(first / step) * step; lag <= last; lag += step) if (lag !== 1 && lag >= first) ticks.push(lag)
  return ticks
}

function signed(value: number, decimals: number): string {
  const text = Math.abs(value).toFixed(decimals)
  return value < 0 && Number(text) !== 0 ? `−${text}` : text
}

/** The cursor's readout for one bar: lag, value, band, and whether the bar is past it. */
export function readoutText(label: string, bar: CorrelogramBar): string {
  return `lag ${bar.lag} · ${label} ${signed(bar.value, 4)} · band ±${bar.band.toFixed(4)}${bar.outside ? ' · beyond the band' : ''}`
}

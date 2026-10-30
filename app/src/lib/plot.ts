/**
 * Pure helpers for the SVG plots: scales, tick positions, segment runs and gap-aware paths.
 *
 * These are presentation transforms (ADR-0001): they map values the JSON already holds to pixels
 * and labels. None of them produces a number of the study.
 */

export type Extent = [number, number]

/** Smallest and largest finite value across every series; null values (gaps) are skipped. */
export function extent(series: readonly (readonly (number | null)[])[]): Extent | null {
  let lo = Infinity
  let hi = -Infinity
  for (const values of series) {
    for (const v of values) {
      if (v === null || !Number.isFinite(v)) continue
      if (v < lo) lo = v
      if (v > hi) hi = v
    }
  }
  return lo <= hi ? [lo, hi] : null
}

/** A linear map from a data interval to a pixel interval. A zero-width domain maps to the middle. */
export function linearScale([d0, d1]: Extent, [r0, r1]: Extent): (v: number) => number {
  const span = d1 - d0
  if (span === 0) return () => (r0 + r1) / 2
  return (v) => r0 + ((v - d0) / span) * (r1 - r0)
}

/** The "nice" step (1, 2 or 5 times a power of ten) closest to range / target. */
export function niceStep(range: number, target: number): number {
  if (!(range > 0) || !(target > 0)) return 1
  const raw = range / target
  const power = 10 ** Math.floor(Math.log10(raw))
  const fraction = raw / power
  const nice = fraction < 1.5 ? 1 : fraction < 3 ? 2 : fraction < 7 ? 5 : 10
  return nice * power
}

/**
 * Decimals needed to print multiples of a nice step exactly: 0.5 -> 1, 0.05 -> 2, 20 -> 0. Nice
 * steps are 1, 2 or 5 times a power of ten, so one decimal per power of ten below 1 is enough.
 */
export function stepDecimals(step: number): number {
  if (!(step > 0) || step >= 1) return 0
  return Math.min(10, Math.ceil(-Math.log10(step) - 1e-9))
}

/**
 * Tick values at multiples of a nice step inside [lo, hi], about `target` of them. Each value is
 * rounded to the step's decimals, so 0.1 + 0.2 never shows up as 0.30000000000000004.
 */
export function niceTicks(lo: number, hi: number, target = 5): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return []
  if (lo === hi) return [lo]
  const step = niceStep(hi - lo, target)
  const decimals = stepDecimals(step) + 1
  const first = Math.ceil(lo / step - 1e-9)
  const last = Math.floor(hi / step + 1e-9)
  const ticks: number[] = []
  for (let k = first; k <= last; k++) ticks.push(Number((k * step).toFixed(decimals)))
  return ticks
}

/** Text for a tick value: as many decimals as the step needs, and "−" for negatives. */
export function formatTick(value: number, step: number): string {
  const text = value.toFixed(stepDecimals(step))
  // -0.00 would read as a negative zero; show it as 0.
  return Number(text) === 0 ? text.replace('-', '') : text.replace('-', '−')
}

export interface Run<T> {
  value: T
  from: number
  to: number
}

/** Consecutive runs of equal values: ['a','a','b'] -> [{a, 0, 1}, {b, 2, 2}] (both ends inclusive). */
export function runs<T>(values: readonly T[]): Run<T>[] {
  const out: Run<T>[] = []
  values.forEach((value, i) => {
    const last = out[out.length - 1]
    if (last && last.value === value) last.to = i
    else out.push({ value, from: i, to: i })
  })
  return out
}

export interface IndexTick {
  index: number
  label: string
}

/**
 * The first row of each calendar year, labelled with the year: x-axis ticks for a series of
 * ISO dates. When there are more than `maxTicks` years, every k-th year is kept.
 */
export function yearTicks(dates: readonly string[], maxTicks = 12): IndexTick[] {
  const ticks: IndexTick[] = []
  let year = ''
  dates.forEach((date, index) => {
    const y = date.slice(0, 4)
    if (y !== year) {
      ticks.push({ index, label: y })
      year = y
    }
  })
  const every = Math.max(1, Math.ceil(ticks.length / maxTicks))
  return ticks.filter((_, k) => k % every === 0)
}

/** Index of the value in ascending `xs` closest to `x` (the lower one on a tie); -1 when empty. */
export function nearestIndex(xs: readonly number[], x: number): number {
  if (xs.length === 0) return -1
  let lo = 0
  let hi = xs.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (xs[mid] <= x) lo = mid
    else hi = mid
  }
  return Math.abs(x - xs[lo]) <= Math.abs(xs[hi] - x) ? lo : hi
}

/**
 * An SVG path through the points, broken wherever y is null: "M x y L x y ... M x y ...".
 * A null is a gap in the data (for example the ends of a centred moving average), so the line
 * must stop there rather than jump across it.
 */
export function gapPath(xs: readonly number[], ys: readonly (number | null)[], sx: (v: number) => number, sy: (v: number) => number): string {
  const parts: string[] = []
  let pen = false
  for (let i = 0; i < xs.length; i++) {
    const y = ys[i]
    if (y === null || y === undefined || !Number.isFinite(y)) {
      pen = false
      continue
    }
    parts.push(`${pen ? 'L' : 'M'}${round2(sx(xs[i]))} ${round2(sy(y))}`)
    pen = true
  }
  return parts.join(' ')
}

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

/** Mantissas for log-axis ticks, coarsest first: 1, 2 and 5 times powers of ten, then finer steps. */
const LOG_MANTISSAS: readonly (readonly number[])[] = [[1], [1, 2, 5], [1, 1.5, 2, 3, 5, 7], [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9]]

/**
 * Tick values for a log axis over [lo, hi], lo > 0: the coarsest mantissa set that gives at least
 * three ticks inside the range. A range too narrow for any (under about 20%) is close to linear, so
 * it gets niceTicks. Each value is rounded to 12 significant digits, so 3 × 10⁻¹ is 0.3.
 */
export function logTicks(lo: number, hi: number, target = 5): number[] {
  if (!(lo > 0) || !Number.isFinite(hi) || !(hi > lo)) return lo > 0 && lo === hi ? [lo] : []
  const first = Math.floor(Math.log10(lo))
  const last = Math.ceil(Math.log10(hi))
  for (const mantissas of LOG_MANTISSAS) {
    const ticks: number[] = []
    for (let e = first; e <= last; e++) {
      for (const m of mantissas) {
        const v = Number((m * 10 ** e).toPrecision(12))
        if (v >= lo && v <= hi) ticks.push(v)
      }
    }
    if (ticks.length >= 3) return ticks
  }
  return niceTicks(lo, hi, target)
}

/** A log-axis tick as text: up to six significant digits, no trailing zeros (150, 0.5, 1500). */
export function formatLogTick(value: number): string {
  return String(Number(value.toPrecision(6)))
}

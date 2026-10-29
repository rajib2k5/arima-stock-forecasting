/**
 * Presentation logic for the price explorer: which values to plot, the shaded segments, tick
 * labels and readouts. Pure and unit-tested; the view only arranges what these return.
 *
 * Nothing here computes a statistic. The dollar axis plots `close_usd` and the log axis plots
 * `log_close`, both straight from prices.json; the app never takes a log or an exp itself.
 */
import type { DecompositionRow, Eda, Kde, PriceRow, Prices, Segment } from './contract.payloads'
import type { PlotBand, PlotSeries, PlotTick } from './SeriesPlot'
import { runs, yearTicks } from './plot'

export type Axis = 'usd' | 'log'

export const SEGMENT_LABELS: Record<Segment, string> = {
  train: 'Train',
  test: 'Test',
  oos: 'Out of sample',
}

export function usd(value: number): string {
  return `$${value.toFixed(2)}`
}

/** A signed number with a fixed count of decimals and a real minus sign. */
export function signed(value: number, decimals: number): string {
  const text = Math.abs(value).toFixed(decimals)
  return value < 0 && Number(text) !== 0 ? `−${text}` : text
}

export interface PricePlot {
  xs: number[]
  series: PlotSeries[]
  yLabel: string
  bands: PlotBand[]
  xTicks: PlotTick[]
  readout: (i: number) => string
}

/** One band per segment run, labelled with its name, dates and row count from `splits`. */
export function segmentBands(prices: Prices): PlotBand[] {
  return runs(prices.rows.map((r) => r.segment)).map((run) => {
    const span = prices.splits[run.value]
    return { from: run.from, to: run.to, kind: run.value, label: `${SEGMENT_LABELS[run.value]}: ${span.start} to ${span.end}, ${span.n} trading ${span.n === 1 ? 'day' : 'days'}` }
  })
}

export function pricePlot(prices: Prices, axis: Axis): PricePlot {
  const rows: PriceRow[] = prices.rows
  // x is the row position: one step per trading day, so weekends and holidays leave no gaps.
  const xs = rows.map((_, i) => i)
  const ys = rows.map((r) => (axis === 'usd' ? r.close_usd : r.log_close))
  return {
    xs,
    series: [{ name: axis === 'usd' ? 'Adjusted close' : 'Log of adjusted close', ys, tone: 'primary' }],
    yLabel: axis === 'usd' ? 'adjusted close ($)' : 'log price, ln($)',
    bands: segmentBands(prices),
    xTicks: yearTicks(rows.map((r) => r.date)).map((t) => ({ x: t.index, label: t.label })),
    readout: (i) => {
      const r = rows[i]
      return `${r.date} · ${usd(r.close_usd)} · ln ${r.log_close.toFixed(4)} · ${SEGMENT_LABELS[r.segment]}`
    },
  }
}

export interface KdeMeta {
  title: string
  xLabel: string
  decimals: number
}

const KDE_META: Record<string, KdeMeta> = {
  log_close: { title: 'Log price, ln($)', xLabel: 'ln($)', decimals: 2 },
  log_return: { title: 'Daily log return', xLabel: 'log points', decimals: 4 },
}

/** Labels for a KDE. `variable` is an open enum, so an unknown one gets a generic label. */
export function kdeMeta(variable: string): KdeMeta {
  return KDE_META[variable] ?? { title: variable, xLabel: variable, decimals: 4 }
}

export interface KdePlot {
  xs: number[]
  series: PlotSeries[]
  readout: (i: number) => string
}

export function kdePlot(kde: Kde): KdePlot {
  const meta = kdeMeta(kde.variable)
  return {
    xs: kde.points.map((p) => p.x),
    series: [
      { name: 'Kernel density estimate', ys: kde.points.map((p) => p.density), tone: 'primary' },
      { name: 'Normal, same mean and sd', ys: kde.points.map((p) => p.normal_density), tone: 'muted', dashed: true },
    ],
    readout: (i) => {
      const p = kde.points[i]
      return `x ${signed(p.x, meta.decimals)} · density ${p.density.toPrecision(4)} · normal ${p.normal_density.toPrecision(4)}`
    },
  }
}

/** The KDEs in the order the explorer shows them: the known variables first, then any others. */
export function orderedKdes(eda: Eda): Kde[] {
  const rank = (k: Kde) => {
    const i = Object.keys(KDE_META).indexOf(k.variable)
    return i < 0 ? Number.MAX_SAFE_INTEGER : i
  }
  return [...eda.kdes].sort((a, b) => rank(a) - rank(b))
}

export const DECOMPOSITION_PARTS = [
  { key: 'observed_log', title: 'Observed', tone: 'primary' },
  { key: 'trend_log', title: 'Trend (centred moving average)', tone: 'primary' },
  { key: 'seasonal_log', title: 'Seasonal', tone: 'secondary' },
  { key: 'resid_log', title: 'Residual', tone: 'muted' },
] as const satisfies readonly { key: keyof DecompositionRow; title: string; tone: PlotSeries['tone'] }[]

export function decompositionXTicks(rows: readonly DecompositionRow[]): PlotTick[] {
  return yearTicks(rows.map((r) => r.date), 9).map((t) => ({ x: t.index, label: t.label }))
}

/** How many rows at the start and at the end have no trend: the half-window of the moving average. */
export function nullEnds(rows: readonly DecompositionRow[]): { head: number; tail: number } {
  const head = rows.findIndex((r) => r.trend_log !== null)
  if (head < 0) return { head: rows.length, tail: 0 }
  let tail = 0
  for (let i = rows.length - 1; i >= 0 && rows[i].trend_log === null; i--) tail++
  return { head, tail }
}

export function shortSha(sha: string): string {
  return sha.slice(0, 12)
}

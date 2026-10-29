/**
 * Geometry and words for the AIC landscape: one d at a time, never two d on one AIC axis
 * (ADR-0002 section 3: d comes from the unit-root tests, and AIC is compared only within one d).
 *
 * Pure. The height of a cell is its exported AIC mapped onto the scene's AIC axis, a presentation
 * transform like a plot scale; the app derives no statistic. Scene coordinates follow aicAxes.ts:
 * p along +x, q along +z, AIC up +y, so the lowest point of the landscape is the best fit.
 */
import { AIC_AXIS_HEIGHT, LABEL_OFFSET, type Vec3 } from './aicAxes'
import type { AicCell, AicGrid, CellStatus, TrendCode } from './contract.order'
import { niceStep, niceTicks, stepDecimals } from './plot'

export const TREND_LABELS: Record<TrendCode, string> = { n: 'no drift (n)', c: 'constant (c)', t: 'drift (t)' }

export const STATUS_LABELS: Record<CellStatus, string> = {
  ok: 'ok',
  not_converged: 'not converged',
  near_unit_root: 'near unit root',
  failed: 'failed',
}

/** Short marks for the table, explained in its legend. */
export const STATUS_MARKS: Record<CellStatus, string> = { ok: '', not_converged: 'nc', near_unit_root: 'nu', failed: '' }

/**
 * Where a failed cell is marked: below the floor, outside the AIC axis. The floor (y = 0) is where
 * the lowest AIC sits, so a failure marked there could be read as the best fit.
 */
export const FAILED_Y = -0.45

export interface LandscapePoint {
  cell: AicCell
  /** Where the marker sits. A failed cell has no AIC; it is marked below the floor, at FAILED_Y. */
  position: Vec3
  selected: boolean
}

export interface LandscapeSegment {
  trend: TrendCode
  from: Vec3
  to: Vec3
}

export interface AicTick {
  value: number
  label: string
  at: Vec3
  labelAt: Vec3
}

export interface Landscape {
  points: LandscapePoint[]
  segments: LandscapeSegment[]
  ticks: AicTick[]
  /** Lowest and highest AIC drawn, or null when no drawn cell has one. */
  range: [number, number] | null
}

/** The d values of the grid, in its order. */
export function gridDs(grid: AicGrid): number[] {
  return grid.grid.specs.map((s) => s.d)
}

export function trendsForD(grid: AicGrid, d: number): TrendCode[] {
  return grid.grid.specs.find((s) => s.d === d)?.trends ?? []
}

export function isSelected(grid: AicGrid, cell: AicCell): boolean {
  const s = grid.selection
  return cell.d === s.d_selected && cell.p === s.order[0] && cell.q === s.order[2] && cell.trend === s.trend
}

/** A number with a plain ASCII minus: the 3D labels' font covers only Basic Latin (AicLandscapeScene.test.tsx). */
export function asciiNumber(value: number, decimals: number): string {
  const text = value.toFixed(decimals)
  return Number(text) === 0 ? text.replace('-', '') : text
}

/**
 * The landscape of one d, for the given trends of that d. Heights share one scale across the
 * trends shown, which is allowed: they are the same d, scored on the same observations.
 */
export function landscape(grid: AicGrid, d: number, trends: readonly TrendCode[], height: number = AIC_AXIS_HEIGHT): Landscape {
  const cells = grid.cells.filter((c) => c.d === d && trends.includes(c.trend))
  const aics = cells.flatMap((c) => (c.aic === null ? [] : [c.aic]))
  const range: [number, number] | null = aics.length > 0 ? [Math.min(...aics), Math.max(...aics)] : null
  const y = (aic: number | null): number => {
    if (aic === null) return FAILED_Y
    if (range === null) return 0
    return range[1] === range[0] ? height / 2 : ((aic - range[0]) / (range[1] - range[0])) * height
  }
  const points = cells.map((cell) => ({ cell, position: [cell.p, y(cell.aic), cell.q] as Vec3, selected: isSelected(grid, cell) }))
  const at = new Map(points.map((pt) => [`${pt.cell.trend} ${pt.cell.p} ${pt.cell.q}`, pt]))
  const segments: LandscapeSegment[] = []
  for (const pt of points) {
    if (pt.cell.aic === null) continue
    for (const [dp, dq] of [
      [1, 0],
      [0, 1],
    ]) {
      const next = at.get(`${pt.cell.trend} ${pt.cell.p + dp} ${pt.cell.q + dq}`)
      if (next && next.cell.aic !== null) segments.push({ trend: pt.cell.trend, from: pt.position, to: next.position })
    }
  }
  let ticks: AicTick[] = []
  if (range !== null && range[1] > range[0]) {
    const step = niceStep(range[1] - range[0], 4)
    const decimals = stepDecimals(step)
    ticks = niceTicks(range[0], range[1], 4).map((value) => {
      const h = y(value)
      return { value, label: asciiNumber(value, decimals), at: [0, h, 0], labelAt: [-LABEL_OFFSET * 3, h, -LABEL_OFFSET] }
    })
  }
  return { points, segments, ticks, range }
}

/** The text of one table cell: delta AIC (or "failed"), and a mark for a cell that cannot be chosen. */
export function cellText(cell: AicCell): string {
  if (cell.status === 'failed') return 'failed'
  const delta = cell.delta_aic === null ? (cell.aic === null ? '–' : 'n/a') : signedOne(cell.delta_aic)
  const mark = STATUS_MARKS[cell.status]
  return mark ? `${delta} ${mark}` : delta
}

function signedOne(value: number): string {
  const text = Math.abs(value).toFixed(1)
  return value < 0 && Number(text) !== 0 ? `−${text}` : text
}

/** A full description of a cell, for its tooltip and screen readers. */
export function cellDescription(cell: AicCell, selected: boolean): string {
  const name = `ARIMA(${cell.p}, ${cell.d}, ${cell.q}), ${TREND_LABELS[cell.trend]}`
  if (cell.status === 'failed') return `${name}: the fit failed (${cell.error ?? 'no message'})`
  const parts = [`AIC ${cell.aic?.toFixed(3)}`, cell.delta_aic === null ? 'no eligible cell at this d' : `ΔAIC ${cell.delta_aic.toFixed(3)}`, STATUS_LABELS[cell.status]]
  if (cell.reason) parts.push(cell.reason)
  if (selected) parts.push('the chosen model')
  return `${name}: ${parts.join('; ')}`
}

/** Rows (p) by columns (q) of one trend's cells, for the table. */
export function cellTable(grid: AicGrid, d: number, trend: TrendCode): (AicCell | undefined)[][] {
  return grid.grid.p.map((p) => grid.grid.q.map((q) => grid.cells.find((c) => c.d === d && c.trend === trend && c.p === p && c.q === q)))
}

/** "ARIMA(3, 1, 5) with a drift" for a cell reference. */
export function modelName(p: number, d: number, q: number, trend: TrendCode | null): string {
  const tail = trend === 't' ? ' with a drift' : trend === 'c' ? ' with a constant' : trend === 'n' ? ' without a drift' : ''
  return `ARIMA(${p}, ${d}, ${q})${tail}`
}


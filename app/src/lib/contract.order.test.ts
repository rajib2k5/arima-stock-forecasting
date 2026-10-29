/**
 * Unit tests of the milestone-2 parsers beyond the shared corpus (contract.payloads.corpus.test.ts
 * runs every corpus case through them): what they return, and the messages they give.
 */
import { describe, expect, it } from 'vitest'
import { parseAcfPacf, parseAicGrid, parseStationarity, tableVerdict } from './contract.order'
import stationarityData from '../test/fixtures/stationarity.data.json'
import acfPacfData from '../test/fixtures/acf_pacf.data.json'
import aicGridData from '../test/fixtures/aic_grid.data.json'

const copy = <T>(x: T): T => structuredClone(x)

describe('tableVerdict, the 2 x 2 table', () => {
  it('maps each pair of rejections to its verdict', () => {
    expect(tableVerdict(true, false)).toBe('stationary')
    expect(tableVerdict(false, true)).toBe('unit_root')
    expect(tableVerdict(true, true)).toBe('conflict')
    expect(tableVerdict(false, false)).toBe('inconclusive')
  })
})

describe('parseStationarity', () => {
  it('returns a fresh object built from the known keys only', () => {
    const data = copy(stationarityData) as Record<string, unknown>
    data.extra = 'ignored'
    const r = parseStationarity(data)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.stationarity).not.toHaveProperty('extra')
    expect(r.stationarity.decision.d_selected).toBe(1)
    expect(r.stationarity.transforms.map((t) => [t.id, t.verdict, t.with_trend.verdict])).toEqual([
      ['log', 'unit_root', 'unit_root'],
      ['diff1', 'stationary', 'stationary'],
      ['diff2', 'stationary', 'stationary'],
    ])
    expect(r.stationarity.transforms[0].kpss.p_value_bound).toBe('smaller')
    expect(r.stationarity.transforms[1].with_trend.kpss.p_value_bound).toBeNull()
  })

  it('names the path of a broken rule', () => {
    const data = copy(stationarityData)
    data.decision.d_selected = 2
    const r = parseStationarity(data)
    expect(r.ok ? [] : r.errors).toContain('data.decision: says d = 2 with tests_conflict false, but the rule gives d = 1 with false')
  })

  it('refuses a payload that is not an object', () => {
    expect(parseStationarity([])).toEqual({ ok: false, errors: ['data: expected an object, got array'] })
  })
})

describe('parseAcfPacf', () => {
  it('returns every series with its rows', () => {
    const r = parseAcfPacf(copy(acfPacfData))
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.acfPacf.series.map((s) => [s.transform, s.rows.length])).toEqual([
      ['log', 4],
      ['diff1', 4],
      ['diff2', 4],
    ])
    expect(r.acfPacf.series[2].rows[1]).toEqual({ lag: 1, acf: -0.5, pacf: -0.5, acf_band: 0.114, pacf_band: 0.114, acf_outside: true, pacf_outside: true })
  })

  it('names the lag whose band is wrong', () => {
    const data = copy(acfPacfData)
    data.series[1].rows[1].pacf_band = 0
    const r = parseAcfPacf(data)
    expect(r.ok ? [] : r.errors).toEqual(['data.series[1].rows[1].pacf_band: is 0; a band is 0 at lag 0 and positive at every other lag'])
  })
})

describe('parseAicGrid', () => {
  it('returns the cells, the selection and the cross-check', () => {
    const r = parseAicGrid(copy(aicGridData))
    expect(r.ok).toBe(true)
    if (!r.ok) return
    const g = r.aicGrid
    expect(g.cells).toHaveLength(16)
    expect(g.selection.order).toEqual([0, 1, 1])
    expect(g.selection.within_2_aic.map((w) => [w.p, w.q, w.trend])).toEqual([
      [0, 1, 't'],
      [1, 0, 't'],
      [0, 1, 'n'],
    ])
    expect(g.selection.best_per_d.map((e) => e.cell && [e.cell.p, e.cell.q])).toEqual([[0, 1], [0, 1], [1, 0]])
    expect(g.pmdarima_check.runs.map((run) => [run.label, run.agreement.same_order_status])).toEqual([
      ['course', 'ok'],
      ['defaults', 'not_converged'],
    ])
    const failed = g.cells.find((c) => c.status === 'failed')!
    expect([failed.aic, failed.delta_aic, failed.error]).toEqual([null, null, 'LinAlgError: made-up failure for the corpus'])
  })

  it('says which delta_aic was measured from the wrong best', () => {
    const data = copy(aicGridData)
    data.cells[12].delta_aic = 297
    const r = parseAicGrid(data)
    expect(r.ok ? [] : r.errors).toContain('data.cells[12].delta_aic: is 297, but aic minus the lowest eligible AIC of d = 2 is 150.5')
  })

  it('refuses a payload that is not an object', () => {
    expect(parseAicGrid(null)).toEqual({ ok: false, errors: ['data: expected an object, got null'] })
  })
})

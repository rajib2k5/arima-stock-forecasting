import { describe, expect, it } from 'vitest'
import { AIC_AXIS_HEIGHT } from './aicAxes'
import { FAILED_Y, asciiNumber, cellDescription, cellTable, cellText, gridDs, isSelected, landscape, modelName, trendsForD } from './aicLandscape'
import { fixtureAicGrid } from '../test/fixtures/payloads'

// The made-up grid (src/test/fixtures/aic_grid.data.json): p, q in {0, 1}; d = 0 with c, d = 1 with
// n and t, d = 2 with n. At d = 1 the chosen cell is (0, 1, 1) with a drift, AIC -1797.0.

describe('grid lookups', () => {
  it('lists the d values and the trends of each d', () => {
    const grid = fixtureAicGrid()
    expect(gridDs(grid)).toEqual([0, 1, 2])
    expect(trendsForD(grid, 1)).toEqual(['n', 't'])
    expect(trendsForD(grid, 7)).toEqual([])
  })

  it('knows the chosen cell and nothing else', () => {
    const grid = fixtureAicGrid()
    expect(grid.cells.filter((c) => isSelected(grid, c)).map((c) => [c.d, c.p, c.q, c.trend])).toEqual([[1, 0, 1, 't']])
  })
})

describe('landscape heights', () => {
  it('puts the lowest AIC of the drawn surface on the floor and the highest at the top', () => {
    const grid = fixtureAicGrid()
    const scape = landscape(grid, 1, ['n', 't'])
    // d = 1 cells with an AIC: -1790.0 ... -1797.0 (the failed (1, 1, 1) t has none).
    expect(scape.range).toEqual([-1797.0, -1790.0])
    const at = (p: number, q: number, t: string) => scape.points.find((pt) => pt.cell.p === p && pt.cell.q === q && pt.cell.trend === t)!
    expect(at(0, 1, 't').position).toEqual([0, 0, 1])
    expect(at(0, 0, 'n').position).toEqual([0, AIC_AXIS_HEIGHT, 0])
    // -1793.0 is 4/7 of the way up from -1797 to -1790
    expect(at(0, 0, 't').position[1]).toBeCloseTo((4 / 7) * AIC_AXIS_HEIGHT, 12)
    expect(at(0, 1, 't').selected).toBe(true)
  })

  it('marks a failed cell below the floor, never at the height of the best cell, and joins it to no neighbour', () => {
    const scape = landscape(fixtureAicGrid(), 1, ['t'])
    const failed = scape.points.find((pt) => pt.cell.status === 'failed')!
    expect(failed.position).toEqual([1, FAILED_Y, 1])
    expect(FAILED_Y).toBeLessThan(0)
    const lowest = Math.min(...scape.points.filter((pt) => pt.cell.status !== 'failed').map((pt) => pt.position[1]))
    expect(lowest).toBe(0) // the best cell of the surface is on the floor ...
    expect(failed.position[1]).toBeLessThan(lowest) // ... and the failure is not
    // t surface: (0,0)-(1,0), (0,0)-(0,1); the failed (1,1) adds nothing
    expect(scape.segments).toHaveLength(2)
    expect(scape.segments.every((s) => s.trend === 't')).toBe(true)
  })

  it('never mixes two d: each surface is scaled on its own AIC range', () => {
    const grid = fixtureAicGrid()
    expect(landscape(grid, 0, ['c']).range).toEqual([-1800.0, -1000.5])
    expect(landscape(grid, 2, ['n']).range).toEqual([-1785.0, -1500.0])
    expect(landscape(grid, 0, ['c']).points.every((pt) => pt.cell.d === 0)).toBe(true)
  })

  it('labels the AIC axis with plain ASCII minus signs at nice steps', () => {
    const ticks = landscape(fixtureAicGrid(), 1, ['n', 't']).ticks
    expect(ticks.map((t) => t.label)).toEqual(['-1796', '-1794', '-1792', '-1790'])
    for (const t of ticks) expect(t.label).toMatch(/^[-0-9.]+$/)
    expect(asciiNumber(-0.0001, 2)).toBe('0.00')
  })

  it('draws a single cell at mid height and gives no ticks when there is no range', () => {
    const grid = fixtureAicGrid()
    grid.cells = grid.cells.filter((c) => c.d === 1 && c.trend === 't' && c.p === 0 && c.q === 1)
    const scape = landscape(grid, 1, ['t'])
    expect(scape.points[0].position[1]).toBe(AIC_AXIS_HEIGHT / 2)
    expect(scape.ticks).toEqual([])
  })
})

describe('the table', () => {
  it('writes delta AIC with a status mark, and "failed" for a failed fit', () => {
    const grid = fixtureAicGrid()
    const t = cellTable(grid, 1, 't')
    expect(t.map((row) => row.map((c) => (c ? cellText(c) : '')))).toEqual([
      ['4.0', '0.0'],
      ['0.3', 'failed'],
    ])
    const n = cellTable(grid, 1, 'n')
    expect(cellText(n[1][0]!)).toBe('1.8 nc')
    expect(cellText(cellTable(grid, 0, 'c')[1][0]!)).toBe('−699.8 nu')
  })

  it('describes a cell fully for its tooltip', () => {
    const grid = fixtureAicGrid()
    const chosen = grid.cells.find((c) => isSelected(grid, c))!
    expect(cellDescription(chosen, true)).toBe('ARIMA(0, 1, 1), drift (t): AIC -1797.000; ΔAIC 0.000; ok; the chosen model')
    const failed = grid.cells.find((c) => c.status === 'failed')!
    expect(cellDescription(failed, false)).toBe('ARIMA(1, 1, 1), drift (t): the fit failed (LinAlgError: made-up failure for the corpus)')
    const nc = grid.cells.find((c) => c.status === 'not_converged')!
    expect(cellDescription(nc, false)).toContain('not converged; L-BFGS did not converge')
  })

  it('names models in words', () => {
    expect(modelName(3, 1, 5, 't')).toBe('ARIMA(3, 1, 5) with a drift')
    expect(modelName(2, 1, 2, 'n')).toBe('ARIMA(2, 1, 2) without a drift')
    expect(modelName(0, 0, 5, 'c')).toBe('ARIMA(0, 0, 5) with a constant')
    expect(modelName(1, 2, 0, null)).toBe('ARIMA(1, 2, 0)')
  })
})

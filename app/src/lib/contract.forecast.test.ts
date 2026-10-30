/**
 * Unit tests of the milestone-4 parsers beyond the shared corpus (contract.payloads.corpus.test.ts
 * runs every corpus case through them): what they return, the messages they give, the bounds they
 * apply before reading, and the rules they leave to Python (ADR-0001: no number is re-checked here).
 */
import { describe, expect, it } from 'vitest'
import {
  ALPHA,
  DM_SETTINGS,
  expectedRefits,
  FORECASTS,
  KINDS,
  LEVELS,
  MAX_D,
  MAX_PQ,
  MAX_ROWS,
  MAX_WARNINGS,
  METHOD_LABELS,
  MODEL_LABELS,
  methodsOf,
  MODEL_IDS,
  NORMAL_Z,
  paramNames,
  parseEvaluation,
  parseForecast,
  REFIT_EVERY,
  type Method,
  type ModelId,
} from './contract.forecast'
import * as fitModule from './contract.fit'
import { forecastData } from '../test/fixtures/payloads'
import evaluationData from '../test/fixtures/evaluation.data.json'

type Json = Record<string, unknown>
type Row = Record<string, unknown>
type Window = { id: string; start: string; end: string; n: number; origin: Row; rows: Row[] }
type Refit = { start_date: string; n_obs: number; params: { name: string; value: number }[] }

const copy = <T>(x: T): T => structuredClone(x)
const evaluation = () => copy(evaluationData) as unknown as Json & { dm: Row[]; coverage: Row[]; metrics: Row[]; windows: Row[] }
const errorsOf = (r: { ok: true } | { ok: false; errors: string[] }) => (r.ok ? [] : r.errors)

/** The aic refit file with `extra` more oos rows (dates one day apart after the last, values copied): no number is checked here. */
function longerRefit(extra: number): Json & { windows: Window[]; refits: Refit[] } {
  const data = forecastData('aic', 'refit') as Json & { windows: Window[]; refits: Refit[] }
  const oos = data.windows[1]
  const last = oos.rows[oos.rows.length - 1]
  for (let k = 1; k <= extra; k++) {
    const day = new Date(Date.UTC(2021, 6, 23 + k)).toISOString().slice(0, 10)
    oos.rows.push({ ...last, date: day })
  }
  oos.n = oos.rows.length
  oos.end = oos.rows[oos.rows.length - 1].date as string
  return data
}

describe('the facts this module restates from the fit module', () => {
  it('are the same model ids, order bounds and parameter names', () => {
    // Restated so that the forecast chunk does not bundle contract.fit.ts; a drift between the copies fails here.
    expect(MODEL_IDS).toEqual(fitModule.MODEL_IDS)
    expect([MAX_PQ, MAX_D, MAX_WARNINGS]).toEqual([fitModule.MAX_PQ, fitModule.MAX_D, fitModule.MAX_WARNINGS])
    for (const trend of ['n', 'c', 't'] as const) {
      for (const [p, q] of [[0, 0], [1, 0], [0, 1], [3, 2], [10, 10]]) expect(paramNames(p, q, trend)).toEqual(fitModule.expectedParamNames(p, q, trend))
    }
  })
})

describe('the pinned settings', () => {
  it('hold forecasting.py’s and evaluation.py’s values', () => {
    expect([LEVELS, NORMAL_Z, REFIT_EVERY, ALPHA, MAX_ROWS]).toEqual([[0.8, 0.95], [1.2815515655446004, 1.959963984540054], 21, 0.05, 10000])
    expect(DM_SETTINGS).toEqual({ horizon: 1, errors: 'log', losses: ['squared', 'absolute'], correction: 'harvey_leybourne_newbold', alternative: 'two_sided', baseline: 'random_walk', same_tolerance: 1e-9 })
    expect(FORECASTS.map(([m, meth]) => `${m}_${meth}`)).toEqual(['aic_static', 'aic_walk_forward', 'aic_refit', 'bic_static', 'bic_walk_forward', 'course_static', 'course_walk_forward'])
    expect(KINDS).toEqual({ static: 'multi_step', walk_forward: 'one_step', refit: 'one_step' })
    expect([methodsOf('aic'), methodsOf('bic'), methodsOf('course')]).toEqual([['static', 'walk_forward', 'refit'], ['static', 'walk_forward'], ['static', 'walk_forward']])
  })

  it('count the refits as the contract does: ceil((n_test + n_oos) / 21) - 1', () => {
    expect([expectedRefits(5, 20), expectedRefits(5, 16), expectedRefits(5, 17), expectedRefits(21, 21), expectedRefits(21, 22), expectedRefits(1, 0)]).toEqual([1, 0, 1, 1, 2, 0])
  })
})

describe('parseForecast', () => {
  it.each(FORECASTS.map(([m, meth]) => [m, meth] as const))('reads the made-up %s %s file', (model, method) => {
    const r = parseForecast(forecastData(model, method), model, method)
    expect(errorsOf(r)).toEqual([])
    expect(r.ok && [r.forecast.model_id, r.forecast.method, r.forecast.kind, r.forecast.windows.map((w) => [w.id, w.n, w.rows.length])]).toEqual([
      model,
      method,
      KINDS[method],
      [
        ['test', 5, 5],
        ['oos', 20, 20],
      ],
    ])
  })

  it('returns a fresh object built from the known keys only', () => {
    const data = forecastData('aic', 'refit') as Json & { windows: Window[]; refits: (Refit & Row)[] }
    data.extra = 'ignored'
    data.windows[0].rows[0].extra = 1
    data.refits[0].extra = true
    const r = parseForecast(data, 'aic', 'refit')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.forecast).not.toHaveProperty('extra')
    expect(r.forecast.windows[0].rows[0]).not.toHaveProperty('extra')
    expect(r.forecast.refits?.[0]).not.toHaveProperty('extra')
    expect(r.forecast.refits?.map((e) => [e.start_date, e.n_obs, e.params.map((p) => p.name)])).toEqual([['2021-07-20', 101, ['drift', 'ar.L1', 'ma.L1', 'sigma2']]])
    expect(r.forecast.intervals.levels).toEqual([0.8, 0.95])
    expect(r.forecast.windows[0].origin).toEqual({ date: '2021-06-18', log_close: 3.6007240407427403, close_usd: 36.62474265188091 })
  })

  it.each([
    ['bic', 'refit'],
    ['course', 'refit'],
  ] as const)('refuses to read a %s %s file: no such file is made (the refit is for the primary model only)', (model, method) => {
    const data = forecastData('aic', 'refit')
    data.model_id = model
    expect(parseForecast(data, model, method)).toEqual({
      ok: false,
      errors: [
        `no forecast file is made for model "${model}" and method "${method}"; the files are forecast_aic_static, forecast_aic_walk_forward, forecast_aic_refit, forecast_bic_static, forecast_bic_walk_forward, forecast_course_static, forecast_course_walk_forward`,
      ],
    })
  })

  it('refuses the payload of another file, by the model and method the file name gives', () => {
    expect(errorsOf(parseForecast(forecastData('aic', 'static'), 'aic', 'walk_forward'))).toEqual(['data.method: is "static", but this is the file of method "walk_forward"'])
    expect(errorsOf(parseForecast(forecastData('bic', 'static'), 'course', 'static'))).toEqual([
      'data.model_id: is "bic", but this is the file of model "course"',
      'data.label: is "BIC choice", but this reader labels model "course" "Course refit"', // the label is pinned per model id too
    ])
  })

  it('refuses a payload that is not an object', () => {
    expect(parseForecast([], 'aic', 'static')).toEqual({ ok: false, errors: ['data: expected an object, got array'] })
  })

  it('takes kind, parameters, refit_every and refits from the method, with nulls exactly where the contract puts them', () => {
    const edit = (method: Method, change: (d: Json) => void) => {
      const data = forecastData('aic', method)
      change(data)
      return errorsOf(parseForecast(data, 'aic', method))
    }
    expect(edit('static', (d) => (d.kind = 'one_step'))).toEqual(['data.kind: is "one_step", but method "static" makes "multi_step" forecasts'])
    expect(edit('refit', (d) => (d.parameters = 'train'))).toEqual(['data.parameters: is "train", but method "refit" takes its parameters from "expanding_refit"'])
    expect(edit('walk_forward', (d) => (d.refit_every = 21))).toEqual(['data.refit_every: must be null for method "walk_forward", which does not re-estimate'])
    expect(edit('static', (d) => (d.refits = []))).toEqual(['data.refits: must be null for method "static", which keeps the training parameters'])
    expect(edit('refit', (d) => (d.refit_every = null))).toEqual(['data.refit_every: is null, but the refit method re-estimates every 21 rows'])
    expect(edit('refit', (d) => (d.refits = null))).toEqual(['data.refits: is null, but the refit method lists every re-estimation'])
  })

  it('compares each pinned value exactly: one ulp, or 1e-12, away is another value', () => {
    const edit = (change: (iv: { levels: number[]; normal_z: number[] }, d: Json) => void, method: Method = 'static') => {
      const data = forecastData('aic', method)
      change(data.intervals as { levels: number[]; normal_z: number[] }, data)
      return errorsOf(parseForecast(data, 'aic', method))
    }
    expect(edit((iv) => (iv.levels = [0.8000000000000002, 0.95]))).toEqual(['data.intervals.levels: is [0.8000000000000002,0.95], but this reader draws the intervals at levels [0.8,0.95]'])
    expect(edit((iv) => (iv.normal_z = [1.2815515655446004 + 1e-12, 1.959963984540054]))).toEqual([
      `data.intervals.normal_z: is [${1.2815515655446004 + 1e-12},1.959963984540054], but this reader uses the normal quantiles [1.2815515655446004,1.959963984540054]`,
    ])
    expect(edit((_, d) => (d.refit_every = 20), 'refit')).toEqual(['data.refit_every: is 20, but this reader re-estimates every 21'])
  })

  it('bounds a window’s n before it reads a row: a stated 2 ** 32 is one short error', () => {
    for (const n of [2 ** 32, 1e9, MAX_ROWS + 1, 0]) {
      const data = forecastData('aic', 'static') as Json & { windows: Window[] }
      data.windows[1].n = n
      data.windows[1].rows = ['not a row'] as unknown as Row[] // never read: the bound comes first
      expect(errorsOf(parseForecast(data, 'aic', 'static'))).toEqual([`data.windows[1].n: expected an integer from 1 to 10000, got ${n}`])
    }
  })

  it('gives one short error for a rows list longer than MAX_ROWS, without walking it', () => {
    const data = forecastData('aic', 'static') as Json & { windows: Window[] }
    data.windows[0].rows = new Array(2_000_000).fill(0) as unknown as Row[]
    const t0 = performance.now()
    expect(errorsOf(parseForecast(data, 'aic', 'static'))).toEqual(['data.windows[0].rows: has 2000000 rows, but n is 5'])
    expect(performance.now() - t0).toBeLessThan(1000)
  })

  it.each([2 ** 32, 1e8, 2 ** 53 - 1])('gives one short error for an AR order of %d, before building parameter names from it', (p) => {
    const data = forecastData('aic', 'refit')
    data.order = [p, 1, 1]
    expect(errorsOf(parseForecast(data, 'aic', 'refit'))).toEqual([`data.order[0]: expected an integer from 0 to ${MAX_PQ}, got ${p}`])
  })

  it('gives one short error for a refits list of the wrong length, however long, without walking it', () => {
    const data = forecastData('aic', 'refit')
    data.refits = new Array(1_000_000).fill('not an entry')
    const t0 = performance.now()
    expect(errorsOf(parseForecast(data, 'aic', 'refit'))).toEqual(['data.refits: has 1000000 entries, but the test and oos rows take 1 (one per 21 rows after the first 21)'])
    expect(performance.now() - t0).toBeLessThan(1000)
  })

  it('checks each refit’s start date against its row and its n_obs against the one before, over several refits', () => {
    // 5 test and 40 oos rows: two refits, serving rows 21 and 42 (from 0) of the 45.
    const data = longerRefit(20)
    const second = { ...copy(data.refits[0]), start_date: data.windows[1].rows[37].date as string, n_obs: 122 }
    data.refits.push(second)
    expect(errorsOf(parseForecast(copy(data), 'aic', 'refit'))).toEqual([])
    const wrong = copy(data)
    wrong.refits[1].n_obs = 123
    wrong.refits[1].start_date = data.windows[1].rows[36].date as string
    expect(errorsOf(parseForecast(wrong, 'aic', 'refit'))).toEqual([
      `data.refits[1].start_date: is ${data.windows[1].rows[36].date}, but row 42 (from 0) of the test and oos rows is ${data.windows[1].rows[37].date}`,
      'data.refits[1].n_obs: is 123, but the entry before was fitted on 101 observations and each refit adds 21',
    ])
    // The same file with one refit only: 45 rows take two.
    const short = copy(data)
    short.refits.pop()
    expect(errorsOf(parseForecast(short, 'aic', 'refit'))).toEqual(['data.refits: has 1 entries, but the test and oos rows take 2 (one per 21 rows after the first 21)'])
  })

  it('takes at most 100 warnings a refit, and gives one short error for more, however many', () => {
    const w = { category: 'W', message: 'm' }
    const data = forecastData('aic', 'refit') as Json & { refits: (Refit & { warnings: unknown[] })[] }
    data.refits[0].warnings = new Array(MAX_WARNINGS).fill(w)
    expect(errorsOf(parseForecast(copy(data), 'aic', 'refit'))).toEqual([])
    data.refits[0].warnings = new Array(3_300_000).fill({ category: '' })
    const t0 = performance.now()
    expect(errorsOf(parseForecast(data, 'aic', 'refit'))).toEqual(['data.refits[0].warnings: has 3300000 warnings, more than the 100 a reader takes'])
    expect(performance.now() - t0).toBeLessThan(1000)
  })

  it('names refit parameters for the order and trend, and names the one out of place', () => {
    const data = forecastData('aic', 'refit') as Json & { refits: Refit[] }
    data.refits[0].params[1].name = 'ma.L1'
    data.refits[0].params[2].name = 'ar.L1'
    expect(errorsOf(parseForecast(data, 'aic', 'refit'))).toEqual(['data.refits[0].params[1].name: is "ma.L1", expected "ar.L1"', 'data.refits[0].params[2].name: is "ar.L1", expected "ma.L1"'])
    data.refits[0].params = data.refits[0].params.slice(1)
    expect(errorsOf(parseForecast(data, 'aic', 'refit'))).toEqual(['data.refits[0].params: has 3 parameters, but the order and trend have 4: drift, ar.L1, ma.L1, sigma2'])
  })

  it('checks the dates: ascending, the first and last the window’s, the origin before it, the test window before the oos window', () => {
    const edit = (change: (w: Window[]) => void) => {
      const data = forecastData('aic', 'static') as Json & { windows: Window[] }
      change(data.windows)
      return errorsOf(parseForecast(data, 'aic', 'static'))
    }
    expect(edit((w) => (w[0].rows[2].date = w[0].rows[1].date))).toEqual(['data.windows[0].rows[2].date: 2021-06-22 does not come after 2021-06-22'])
    expect(edit((w) => (w[0].start = '2021-06-20'))).toEqual(['data.windows[0].rows[0].date: is 2021-06-21, but the window starts 2021-06-20'])
    expect(edit((w) => (w[1].end = '2021-07-22'))).toEqual(['data.windows[1].rows[19].date: is 2021-07-23, but the window ends 2021-07-22'])
    expect(edit((w) => (w[0].origin.date = w[0].start))).toEqual(['data.windows[0].origin.date: is 2021-06-21, but the origin is the last day before the window, which starts 2021-06-21'])
    expect(edit((w) => ((w[0].end = '2021-06-28'), (w[0].rows[4].date = '2021-06-28')))).toEqual(['data.windows[1].start: is 2021-06-28, but the test window ends 2021-06-28; the oos window starts after it'])
    expect(edit((w) => w.reverse())).toEqual([
      'data.windows[0].id: is "oos", expected "test" (the windows are "test" then "oos")',
      'data.windows[1].id: is "test", expected "oos" (the windows are "test" then "oos")',
    ])
  })

  it('refuses a forecast with no spread, sd_log 0, and a t on 2 degrees of freedom', () => {
    const data = forecastData('aic', 'static') as Json & { windows: Window[] }
    data.windows[0].rows[0].sd_log = 0
    data.t_df = 2
    expect(errorsOf(parseForecast(data, 'aic', 'static'))).toEqual([
      'data.t_df: must be above 2 (a Student-t on 2 or fewer degrees of freedom has no finite variance), got 2',
      'data.windows[0].rows[0].sd_log: must be above 0 (a forecast with no spread), got 0',
    ])
  })

  it('reads the t quantiles and multipliers as two numbers each, and each refit entry as an object', () => {
    const data = forecastData('aic', 'refit') as Json & { intervals: Row }
    data.intervals.t_quantile = [1.5, 2.6, 3.7]
    data.refits = ['not an entry']
    expect(errorsOf(parseForecast(data, 'aic', 'refit'))).toEqual(['data.intervals.t_quantile: expected 2 numbers, got [1.5,2.6,3.7]', 'data.refits[0]: expected an object, got string'])
  })

  it('quotes a value of any size in a short message', () => {
    const data = forecastData('aic', 'static')
    data.t_df = new Array(1_000_000).fill(1)
    data.label = ' '.repeat(100_000)
    data.trend = 'x'.repeat(100_000)
    const errors = errorsOf(parseForecast(data, 'aic', 'static'))
    expect(errors).toEqual([
      expect.stringMatching(/^data\.label: expected a non-empty string, got " {80}"… \(100000 characters\)$/),
      expect.stringMatching(/^data\.trend: expected one of c, n, t, got "x{80}"… \(100000 characters\)$/),
      'data.t_df: expected a finite number, got an array of 1000000',
    ])
  })

  it('accepts what only Python checks: the dollar values, the t numbers, a falling static spread', () => {
    // Each edit breaks a rule of validate_forecast that recomputes a number (tests/test_payloads_forecast.py); none is the app's.
    const data = forecastData('aic', 'static') as Json & { windows: Window[]; intervals: Row }
    data.windows[0].rows[0].median_usd = 1
    data.windows[0].rows[1].upper_95_usd = 0.5
    data.windows[0].rows[2].actual_usd = 999
    data.windows[0].rows[3].sd_log = 0.001 // falls from row 2's
    data.intervals.t_scale = 3
    data.intervals.t_multiplier = [9, 9]
    expect(errorsOf(parseForecast(data, 'aic', 'static'))).toEqual([])
  })
})

describe('parseEvaluation', () => {
  it('reads the made-up file and returns a fresh object built from the known keys only', () => {
    const data = evaluation()
    data.extra = 1
    data.dm[0].extra = 2
    const r = parseEvaluation(data)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    const e = r.evaluation
    expect(e).not.toHaveProperty('extra')
    expect(e.dm[0]).not.toHaveProperty('extra')
    expect([e.windows.map((w) => [w.id, w.n]), e.models.map((m) => [m.id, m.methods.length]), e.random_walk.length, e.metrics.length, e.dm.length, e.coverage.length]).toEqual([
      [
        ['test', 5],
        ['oos', 20],
      ],
      [
        ['aic', 3],
        ['bic', 2],
        ['course', 2],
      ],
      4,
      14,
      16,
      56,
    ])
    expect(e.coverage[0]).toEqual({ model_id: 'aic', method: 'static', window: 'test', distribution: 'normal', level: 0.8, n: 5, inside: 0, rate: 0, lr: null, p_value: null, verdict: 'not_tested' })
  })

  it('refuses a payload that is not an object', () => {
    expect(parseEvaluation(null)).toEqual({ ok: false, errors: ['data: expected an object, got null'] })
  })

  it('gives one short error for a row set of the wrong length, however long, without walking it', () => {
    const data = evaluation()
    data.coverage = new Array(1_000_000).fill('x')
    data.metrics = data.metrics.slice(1)
    const t0 = performance.now()
    expect(errorsOf(parseEvaluation(data))).toEqual([
      'data.metrics: has 13 rows, expected 14: one per forecast file and window, in FORECASTS order, test before oos',
      'data.coverage: has 1000000 rows, expected 56: one per forecast file, window, distribution (normal, then t) and level (0.8, then 0.95)',
    ])
    expect(performance.now() - t0).toBeLessThan(1000)
  })

  it('names a row out of place by its key and the key its position holds', () => {
    const data = evaluation()
    ;[data.dm[0], data.dm[1]] = [data.dm[1], data.dm[0]]
    expect(errorsOf(parseEvaluation(data))).toEqual([
      'data.dm[0]: is the row of (aic, walk_forward, test, absolute), but this position holds (aic, walk_forward, test, squared)',
      'data.dm[1]: is the row of (aic, walk_forward, test, squared), but this position holds (aic, walk_forward, test, absolute)',
    ])
  })

  it('ties a DM row’s df to its n, and its n to its window', () => {
    const data = evaluation()
    data.dm[0].df = 5
    data.dm[1].n = 6
    expect(errorsOf(parseEvaluation(data))).toEqual(['data.dm[0].df: is 5, but n - 1 is 4', 'data.dm[1].n: is 6, but the test window has 5 rows'])
  })

  it('needs at least two forecasts for a DM row, and a positive var_diff', () => {
    const data = evaluation()
    data.dm[0].n = 1
    data.dm[1].var_diff = 0
    expect(errorsOf(parseEvaluation(data))).toEqual([
      'data.dm[0].n: expected an integer >= 2, got 1',
      'data.dm[1].var_diff: must be above 0 (a constant loss differential leaves DM undefined), got 0',
    ])
  })

  it('reads a model that is the random walk as same_as_rw: no statistic, no p-value, a var_diff of 0 allowed', () => {
    const same = (row: Row) => Object.assign(row, { verdict: 'same_as_rw', max_forecast_gap: 0, mean_diff: 0, var_diff: 0, statistic: null, statistic_hln: null, p_value: null })
    const data = evaluation()
    same(data.dm[0])
    const r = parseEvaluation(data)
    expect(errorsOf(r)).toEqual([])
    expect(r.ok && r.evaluation.dm[0]).toMatchObject({ verdict: 'same_as_rw', var_diff: 0, statistic: null, statistic_hln: null, p_value: null, hln_factor: 0.8944271909999159, df: 4 })
    const edit = (change: (rows: Row[]) => void) => {
      const d = evaluation()
      change(d.dm)
      return errorsOf(parseEvaluation(d))
    }
    expect(edit((rows) => (((same(rows[0]) as Row).statistic = 1.2), ((same(rows[1]) as Row).var_diff = -1e-300)))).toEqual([
      'data.dm[0]: statistic, statistic_hln, p_value must be null where the verdict is "same_as_rw", which is not tested',
      'data.dm[1].var_diff: must be at least 0 (a variance), got -1e-300',
    ])
    expect(edit((rows) => ((rows[2].p_value = null), (rows[3].max_forecast_gap = -1e-12)))).toEqual([
      'data.dm[2]: statistic, statistic_hln, p_value must be numbers where the verdict is "no_difference", which is tested',
      'data.dm[3].max_forecast_gap: must be at least 0 (a distance), got -1e-12',
    ])
    // Which rows are within the tolerance is Python's call: a gap of 0.5 read as same_as_rw passes here.
    expect(edit((rows) => (same(rows[4]).max_forecast_gap = 0.5))).toEqual([])
  })

  it('makes the coverage nulls and "not_tested" exactly the static rows', () => {
    const edit = (i: number, change: (row: Row) => void) => {
      const data = evaluation()
      change(data.coverage[i])
      return errorsOf(parseEvaluation(data))
    }
    expect(edit(0, (row) => (row.lr = 0.5))).toEqual(['data.coverage[0]: lr and p_value must be null for a multi_step forecast, which is not tested'])
    expect(edit(0, (row) => (row.verdict = 'consistent'))).toEqual(['data.coverage[0].verdict: is "consistent", but a multi_step forecast is "not_tested"'])
    expect(edit(8, (row) => (row.p_value = null))).toEqual(['data.coverage[8]: lr and p_value must be numbers for a one_step forecast, which is tested'])
    expect(edit(8, (row) => (row.verdict = 'not_tested'))).toEqual(['data.coverage[8].verdict: is "not_tested", but a one_step forecast is tested'])
    expect(edit(1, (row) => ((row.inside = 6), (row.rate = 1.2)))).toEqual(["data.coverage[1].inside: is 6, more than the window's 5 days"])
    expect(edit(1, (row) => (row.level = 0.9500000000000001))).toEqual(['data.coverage[1].level: is 0.9500000000000001, but this reader expects at this position the level 0.95'])
  })

  it('pins each method’s label, the text of the Method picker, by its id (evaluation.METHOD_LABELS)', () => {
    expect(METHOD_LABELS).toEqual({ static: "Static multi-step (the course's)", walk_forward: 'Walk-forward one-step', refit: 'Walk-forward one-step, refit every 21 days' })
    const data = evaluation() as unknown as Json & { methods: Row[] }
    data.methods[2].label = 'Walk-forward one-step, refit every 5 days'
    data.methods[1].label = "Static multi-step (the course's)"
    expect(errorsOf(parseEvaluation(data))).toEqual([
      `data.methods[1].label: is "Static multi-step (the course's)", but this reader labels method "walk_forward" "Walk-forward one-step"`,
      'data.methods[2].label: is "Walk-forward one-step, refit every 5 days", but this reader labels method "refit" "Walk-forward one-step, refit every 21 days"',
    ])
  })

  it('pins each model’s label, the text of the Model picker, by its id (fitting.LABELS; payloads.MODEL_LABELS)', () => {
    expect(MODEL_LABELS).toEqual({ aic: 'AIC choice (ADR-0002)', bic: 'BIC choice', course: 'Course refit' })
    const data = evaluation() as unknown as Json & { models: Row[] }
    data.models[0].label = 'BIC choice' // the two swapped: each file's own check names both
    data.models[1].label = 'AIC choice (ADR-0002)'
    data.models[2].label = 'Course refit '
    expect(errorsOf(parseEvaluation(data))).toEqual([
      'data.models[0].label: is "BIC choice", but this reader labels model "aic" "AIC choice (ADR-0002)"',
      'data.models[1].label: is "AIC choice (ADR-0002)", but this reader labels model "bic" "BIC choice"',
      'data.models[2].label: is "Course refit ", but this reader labels model "course" "Course refit"',
    ])
    const forecast = forecastData('aic', 'refit') as Row
    forecast.label = 'AIC choice'
    expect(errorsOf(parseForecast(forecast, 'aic', 'refit'))).toEqual(['data.label: is "AIC choice", but this reader labels model "aic" "AIC choice (ADR-0002)"'])
  })

  it('pins alpha, the levels, the refit interval and the DM settings, compared exactly', () => {
    const data = evaluation()
    data.alpha = 0.05 + 1e-12
    data.refit_every = 20
    data.headline_usd = 'mean'
    data.dm_settings = { ...(data.dm_settings as Row), horizon: 2, losses: ['absolute', 'squared'], alternative: 'less', same_tolerance: 1e-9 + 1e-21 }
    expect(errorsOf(parseEvaluation(data))).toEqual([
      `data.alpha: is ${0.05 + 1e-12}, but this reader reads the tests at alpha 0.05`,
      'data.refit_every: is 20, but this reader re-estimates every 21',
      'data.headline_usd: expected "median", got "mean"',
      'data.dm_settings.horizon: is 2, but this reader tests one-step forecasts, horizon 1',
      'data.dm_settings.losses: is ["absolute","squared"], but this reader tests the losses ["squared","absolute"]',
      'data.dm_settings.alternative: expected "two_sided", got "less"',
      `data.dm_settings.same_tolerance: is ${1e-9 + 1e-21}, but this reader reads a model as the random walk within 1e-9`,
    ])
  })

  it('lists the refit for the primary model only, and each method with the kind its forecasts are', () => {
    const data = evaluation() as unknown as Json & { models: { methods: string[] }[]; methods: Row[] }
    data.models[1].methods = ['static', 'walk_forward', 'refit']
    data.methods[2].kind = 'multi_step'
    expect(errorsOf(parseEvaluation(data))).toEqual([
      'data.models[1].methods: is ["static","walk_forward","refit"], but this reader lists model "bic"\'s forecast files as ["static","walk_forward"]',
      'data.methods[2].kind: is "multi_step", but method "refit" makes "one_step" forecasts',
    ])
  })

  it('bounds a window’s n, and checks the window dates', () => {
    const data = evaluation()
    data.windows[1].n = 2 ** 40
    data.windows[0].origin_date = data.windows[0].start
    expect(errorsOf(parseEvaluation(data))).toEqual([
      'data.windows[0].origin_date: is 2021-06-21, but the origin is the last day before the window, which starts 2021-06-21',
      `data.windows[1].n: expected an integer from 1 to 10000, got ${2 ** 40}`,
    ])
    const later = evaluation()
    later.windows[0].end = '2021-06-28'
    later.windows[1].start = '2021-06-27'
    later.windows[1].end = '2021-06-26'
    expect(errorsOf(parseEvaluation(later))).toEqual([
      "data.windows[1].end: is 2021-06-26, before the window's start 2021-06-27",
    ])
  })

  it('accepts what only Python checks: ratios, statistics, p-values against their statistics, rates, and every verdict a p-value decides', () => {
    // Each edit breaks a recomputation of validate_evaluation (tests/test_payloads_forecast.py); none is the app's to check.
    const data = evaluation() as unknown as Json & { dm: Row[]; coverage: Row[]; metrics: { ratio_to_rw: { log: Row } }[] }
    data.metrics[0].ratio_to_rw.log.rmse = 99
    data.dm[0].statistic = 50
    data.dm[0].p_value = 0.9
    data.dm[0].verdict = 'beats_rw'
    data.dm[1].hln_factor = 7
    data.coverage[8].rate = 0.123
    data.coverage[8].lr = 1000
    data.coverage[8].verdict = 'too_wide'
    expect(errorsOf(parseEvaluation(data))).toEqual([])
  })

  it.each(MODEL_IDS.map((id) => [id] as const))('gives the methods of model %s in file order', (id: ModelId) => {
    const r = parseEvaluation(evaluation())
    expect(r.ok && r.evaluation.models.find((m) => m.id === id)?.methods).toEqual(methodsOf(id))
  })
})

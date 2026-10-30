/**
 * Unit tests of the milestone-3 parsers beyond the shared corpus (contract.payloads.corpus.test.ts
 * runs every corpus case through them): what they return, the messages they give, and the rules
 * they leave to Python (ADR-0001: no statistic is re-checked here).
 */
import { describe, expect, it } from 'vitest'
import { ALPHA, ARCH_LM_DDOF, ARCH_LM_LAGS, CANCEL_DISTANCE, defaultTrend, expectedParamNames, LJUNG_BOX_LAGS, LLF_TOLERANCE, MAX_D, MAX_PQ, MAX_WARNINGS, NLAGS, parseFit, parseResiduals } from './contract.fit'
import fitData from '../test/fixtures/fit.data.json'
import residualsData from '../test/fixtures/residuals_aic.data.json'

const copy = <T>(x: T): T => structuredClone(x)

describe('expectedParamNames', () => {
  it('lists the trend term, the AR lags, the MA lags and sigma2, in statsmodels’ order', () => {
    expect(expectedParamNames(2, 2, 't')).toEqual(['drift', 'ar.L1', 'ar.L2', 'ma.L1', 'ma.L2', 'sigma2'])
    expect(expectedParamNames(1, 0, 'c')).toEqual(['const', 'ar.L1', 'sigma2'])
    expect(expectedParamNames(0, 1, 'n')).toEqual(['ma.L1', 'sigma2'])
  })
})

describe('parseFit', () => {
  it('quotes a value of any size in a short message', () => {
    // An order of 200,000 numbers was once quoted whole: 400 kB of text for one error.
    const data = structuredClone(fitData) as unknown as { models: { order: unknown }[] }
    data.models[1].order = new Array(200_000).fill(0)
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toContain('data.models[1].order: expected [p, d, q], got an array of 200000')
    expect((r.ok ? [] : r.errors).join('').length).toBeLessThan(2000)
  })

  it('returns a fresh object built from the known keys only', () => {
    const data = copy(fitData) as Record<string, unknown>
    data.extra = 'ignored'
    const r = parseFit(data)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.fit).not.toHaveProperty('extra')
    expect(r.fit.course_track).not.toHaveProperty('settings')
    expect(r.fit.models.map((m) => [m.id, m.order, m.trend, m.params.length, m.cancelling_pairs.length])).toEqual([
      ['aic', [3, 1, 2], 't', 7, 2],
      ['bic', [1, 1, 0], 'n', 2, 0],
      ['course', [0, 1, 1], 'n', 2, 0],
    ])
    const aic = r.fit.models[0]
    expect(aic.params[0]).toMatchObject({ name: 'drift', library_name: 'x1', value: 0.0009, std_err: 0.0004 })
    expect(aic.diagnostics.ljung_box.map((row) => [row.lag, row.applied, row.df, row.p_value])).toEqual([
      [5, false, null, null],
      [10, true, 5, 0.31607130918509807],
      [20, true, 15, 0.6485345616521715],
    ])
    expect(aic.diagnostics.verdicts).toEqual({ serial_correlation: 'not_found', normality: 'rejected', arch: 'found' })
    expect([r.fit.models[2].grid_llf, r.fit.models[2].llf_gap]).toEqual([null, null])
    expect(r.fit.course_track.same_order).toBe(true)
    expect(r.fit.clustering_prediction).toMatchObject({ model_id: 'aic', confirmed: true, acf_squared_outside_count: 1 })
  })

  it('keeps the five inference fields null when they are null together', () => {
    const data = copy(fitData) as { models: { params: Record<string, unknown>[] }[] }
    for (const k of ['std_err', 'z', 'p_value', 'ci_low', 'ci_high']) data.models[0].params[1][k] = null
    const r = parseFit(data)
    expect(r.ok && r.fit.models[0].params[1]).toEqual({ name: 'ar.L1', library_name: 'ar.L1', value: 0.6, std_err: null, z: null, p_value: null, ci_low: null, ci_high: null })
  })

  it('names the misordered models and the parameter that is out of place', () => {
    const data = copy(fitData)
    data.models[0].id = 'bic'
    data.models[1].id = 'aic'
    data.models[2].params[0].name = 'ar.L1'
    data.models[2].params[0].library_name = 'ar.L1'
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toEqual([
      'data.models: ids are ["bic","aic","course"], expected ["aic","bic","course"] in that order',
      'data.models[2].params[0].name: is "ar.L1", expected "ma.L1"',
    ])
  })

  it('refuses a drift that is not labelled x1, the label statsmodels gives it', () => {
    const data = copy(fitData)
    data.models[0].params[0].library_name = 'drift'
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toEqual(['data.models[0].params[0].library_name: is "drift"; statsmodels labels "drift" as "x1"'])
  })

  it('accepts what only Python checks: z, the p-value, the interval, the moduli, the pairing rule, the verdicts', () => {
    // Each edit breaks a statistic rule of validate_fit (tests/test_payloads_fit.py); none is the app's to check.
    const data = copy(fitData)
    const aic = data.models[0]
    aic.params[1].z = 99
    aic.params[1].p_value = 0.9
    aic.params[1].ci_low = -5
    aic.information.aic = 0
    aic.llf_gap = 7
    aic.inv_roots_ar[0].modulus = 0.9
    aic.cancelling_pairs = []
    aic.diagnostics.verdicts.serial_correlation = 'found'
    aic.diagnostics.verdicts.normality = 'not_rejected'
    data.clustering_prediction.arch_lm_rejections = 0
    data.clustering_prediction.acf_squared_expected_by_chance = 3
    data.course_track.drift_dropped.aic_gap = -100
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toEqual([])
  })

  it('refuses a payload that is not an object', () => {
    expect(parseFit([])).toEqual({ ok: false, errors: ['data: expected an object, got array'] })
  })

  it('pins llf_tolerance at 1e-6 and cancel_distance at 0.1, as fitting.py, and refuses any other stated value', () => {
    expect([LLF_TOLERANCE, CANCEL_DISTANCE]).toEqual([1e-6, 0.1])
    const r = parseFit(copy(fitData))
    expect(r.ok && [r.fit.llf_tolerance, r.fit.cancel_distance]).toEqual([1e-6, 0.1])
    const data = copy(fitData)
    data.llf_tolerance = 1
    data.cancel_distance = 0.2
    const bad = parseFit(data)
    expect(bad.ok ? [] : bad.errors).toEqual([
      "data.cancel_distance: is 0.2, but this reader pairs roots within 0.1",
      "data.llf_tolerance: is 1, but this reader checks the refit's llf at 0.000001",
    ])
  })

  it('compares a stated pin exactly: a value 1e-12 away is another value and is refused', () => {
    const errors = (edit: (d: Record<string, unknown>) => void) => {
      const data = copy(fitData) as unknown as Record<string, unknown>
      edit(data)
      const r = parseFit(data)
      return r.ok ? [] : r.errors
    }
    expect(errors((d) => (d.llf_tolerance = 1e-6 + 1e-12))).toEqual([`data.llf_tolerance: is ${1e-6 + 1e-12}, but this reader checks the refit's llf at 0.000001`])
    expect(errors((d) => (d.cancel_distance = 0.1 + 1e-12))).toEqual([`data.cancel_distance: is ${0.1 + 1e-12}, but this reader pairs roots within 0.1`])
    expect(errors((d) => ((d.diagnostic_settings as Record<string, unknown>).alpha = 0.05 + 1e-12))).toEqual([`data.diagnostic_settings.alpha: is ${0.05 + 1e-12}, but this reader tests at alpha 0.05`])
  })

  it('pins the residual tests’ settings as diagnostics.py, and refuses any other stated value', () => {
    // alpha, the two lag lists, the ddof and nlags: a file that states others changes which rows exist.
    expect([ALPHA, LJUNG_BOX_LAGS, ARCH_LM_LAGS, ARCH_LM_DDOF, NLAGS]).toEqual([0.05, [5, 10, 20], [5, 10], 0, 50])
    const r = parseFit(copy(fitData))
    expect(r.ok && r.fit.diagnostic_settings).toMatchObject({ alpha: 0.05, ljung_box_lags: [5, 10, 20], arch_lm_lags: [5, 10], arch_lm_ddof: 0, nlags: 50 })
    const data = copy(fitData)
    Object.assign(data.diagnostic_settings, { alpha: 0.1, ljung_box_lags: [5, 10, 21], arch_lm_lags: [5], arch_lm_ddof: 1, nlags: 49 })
    const bad = parseFit(data)
    expect(bad.ok ? [] : bad.errors).toEqual([
      'data.diagnostic_settings.alpha: is 0.1, but this reader tests at alpha 0.05',
      'data.diagnostic_settings.ljung_box_lags: is [5,10,21], but this reader checks Ljung-Box at lags [5,10,20]',
      'data.diagnostic_settings.arch_lm_lags: is [5], but this reader checks ARCH-LM at lags [5,10]',
      'data.diagnostic_settings.arch_lm_ddof: is 1, but this reader checks ARCH-LM with ddof 0',
      'data.diagnostic_settings.nlags: is 49, but this reader checks the correlograms at nlags 50',
    ])
  })

  it('refuses a file whose own lags give the course model another serial-correlation verdict', () => {
    // The re-review's probe: ljung_box_lags [5] and every model's rows cut to lag 5, verdicts to match. The
    // course model's goes from "found" (lag 10) to "not_found"; read at its own lags the file agrees with itself.
    const data = copy(fitData)
    data.diagnostic_settings.ljung_box_lags = [5]
    ;(['not_tested', 'found', 'not_found'] as const).forEach((verdict, i) => {
      data.models[i].diagnostics.ljung_box = data.models[i].diagnostics.ljung_box.slice(0, 1)
      data.models[i].diagnostics.verdicts.serial_correlation = verdict
    })
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toEqual([
      'data.diagnostic_settings.ljung_box_lags: is [5], but this reader checks Ljung-Box at lags [5,10,20]',
      ...[0, 1, 2].map((i) => `data.models[${i}].diagnostics.ljung_box: has 1 rows, but ljung_box_lags has 3`),
    ])
  })

  it.each([2 ** 32, 1e8, 2 ** 53 - 1])('gives one short error for an AR order of %d, before building any list from it', (p) => {
    // Before the bound, 2 ** 32 threw a RangeError (an array of that length) and 1e8 ran out of heap.
    const data = copy(fitData)
    data.models[0].order = [p, 1, 2]
    expect(parseFit(data)).toEqual({ ok: false, errors: [`data.models[0].order[0]: expected an integer from 0 to ${MAX_PQ}, got ${p}`] })
  })

  it('takes at most 100 warnings a list, and gives one short error for more, however many', () => {
    // 3.3 million warnings once made 324 MB of messages and took 2.6 s: the bound comes before the list is read.
    expect(MAX_WARNINGS).toBe(100)
    const w = { category: 'W', message: 'm' }
    const data = copy(fitData) as { models: { warnings: unknown[] }[]; course_track: { full_series: { warnings: unknown[] } } }
    data.models[0].warnings = new Array(100).fill(w)
    data.course_track.full_series.warnings = new Array(100).fill(w)
    expect(parseFit(copy(data)).ok).toBe(true)
    data.models[0].warnings = new Array(3_300_000).fill({ category: '' })
    data.course_track.full_series.warnings = new Array(101).fill(w)
    const t0 = performance.now()
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toEqual([
      'data.models[0].warnings: has 3300000 warnings, more than the 100 a reader takes',
      'data.course_track.full_series.warnings: has 101 warnings, more than the 100 a reader takes',
    ])
    expect(performance.now() - t0).toBeLessThan(1000)
  })

  it('bounds p and q by 10 and d by 2, and lets the bounds themselves through', () => {
    expect([MAX_PQ, MAX_D]).toEqual([10, 2])
    const at = (order: number[]) => {
      const data = copy(fitData)
      data.models[1].order = order
      const r = parseFit(data)
      return r.ok ? [] : r.errors.filter((e) => e.includes('.order'))
    }
    expect(at([10, 2, 10])).toEqual([])
    expect(at([11, 1, 0])).toEqual(['data.models[1].order[0]: expected an integer from 0 to 10, got 11'])
    expect(at([1, 3, 0])).toEqual(['data.models[1].order[1]: expected an integer from 0 to 2, got 3'])
    expect(at([1, 1, 11])).toEqual(['data.models[1].order[2]: expected an integer from 0 to 10, got 11'])
  })

  it('keeps sigma2 with a standard error but no z and no p-value, and refuses one with a z', () => {
    const r = parseFit(copy(fitData))
    expect(r.ok && r.fit.models[0].params[6]).toMatchObject({ name: 'sigma2', std_err: 5e-5, z: null, p_value: null, ci_low: 0.0002120018007729973 })
    const data = copy(fitData) as { models: { params: Record<string, unknown>[] }[] }
    data.models[0].params[6].z = 6.2
    data.models[0].params[6].p_value = 5.6e-10
    const bad = parseFit(data)
    expect(bad.ok ? [] : bad.errors).toEqual([
      'data.models[0].params[6]: sigma2 has std_err and its interval, and z and p_value null (its null value 0 is on the boundary, where the z-test does not apply); got no null',
    ])
  })

  it('takes the primary model to be the AIC choice, and nothing else', () => {
    const data = copy(fitData)
    data.primary = 'bic'
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toEqual(['data.primary: expected "aic", got "bic"'])
  })

  it('ties the course model’s trend to statsmodels’ default at its d', () => {
    expect([defaultTrend(0), defaultTrend(1), defaultTrend(2)]).toEqual(['c', 'n', 'n'])
    const data = copy(fitData)
    data.models[2].trend = 't'
    data.course_track.refit_trend = 't'
    data.course_track.drift_dropped.refit_trend = 't'
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toContain("data.models[2].trend: is \"t\", but ARIMA(train, order).fit() at d = 1 has statsmodels' default trend \"n\"")
  })

  it('names a drift whose standard error and p-value are not null together, or whose error is not positive', () => {
    const errors = (edit: (d: { drift_std_err: number | null; drift_p_value: number | null }) => void) => {
      const data = copy(fitData)
      edit(data.course_track.drift_dropped)
      const r = parseFit(data)
      return r.ok ? [] : r.errors
    }
    expect(errors((d) => (d.drift_std_err = null))).toEqual(['data.course_track.drift_dropped: drift_std_err and drift_p_value are null together (a singular covariance)'])
    expect(errors((d) => (d.drift_std_err = 0))).toEqual(['data.course_track.drift_dropped.drift_std_err: must be positive, got 0'])
    expect(errors((d) => ((d.drift_std_err = null), (d.drift_p_value = null)))).toEqual([])
  })

  it('names a selected trend that is not the one the full-series search chose', () => {
    const data = copy(fitData)
    data.course_track.drift_dropped.selected_trend = 'n'
    const r = parseFit(data)
    expect(r.ok ? [] : r.errors).toEqual(['data.course_track.drift_dropped.selected_trend: is "n", but full_series.trend, the trend the search selected, is "t"'])
  })
})

describe('parseResiduals', () => {
  it('returns the rows, both correlograms with Python’s flags, the QQ points and the t fit', () => {
    const r = parseResiduals(copy(residualsData), 'aic')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.residuals.rows).toHaveLength(7)
    expect(r.residuals.acf_squared.rows.map((row) => row.outside)).toEqual([true, false, false])
    expect(r.residuals.qq).toHaveLength(7)
    expect(r.residuals.t_fit).toEqual({ df: 5, loc: 0, scale: 0.9 })
  })

  it('refuses the file of another model', () => {
    const r = parseResiduals(copy(residualsData), 'bic')
    expect(r.ok ? [] : r.errors).toEqual(['data.model_id: expected "bic", got "aic"'])
  })

  it('takes Python’s outside flags as they are, and only counts them', () => {
    const data = copy(residualsData)
    data.acf.rows[0].outside = true // 0.1 is inside the band; Python alone would refuse this
    expect(parseResiduals(data, 'aic').ok).toBe(false)
    data.acf.outside_count = 1
    const r = parseResiduals(data, 'aic')
    expect(r.ok && r.residuals.acf.rows[0]).toEqual({ lag: 1, acf: 0.1, outside: true })
  })

  it('refuses a payload that is not an object', () => {
    expect(parseResiduals('x', 'aic')).toEqual({ ok: false, errors: ['data: expected an object, got string'] })
  })

  it('bounds burn_excluded by d’s bound, 2', () => {
    const data = copy(residualsData)
    data.burn_excluded = 999
    expect(parseResiduals(data, 'aic')).toEqual({ ok: false, errors: ['data.burn_excluded: expected an integer from 0 to 2, got 999'] })
    data.burn_excluded = 2
    expect(parseResiduals(data, 'aic').ok).toBe(true)
  })
})

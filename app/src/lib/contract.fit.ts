/**
 * Payload parsers for the milestone-3 artifacts: `fit` and the three `residuals_<id>` files
 * (contract.md sections 3.7 and 3.8). The Python copy of every rule is in
 * src/arima_forecasting/payloads.py (validate_fit, validate_residuals); the shared corpus
 * (src/test/fixtures/payload_cases.json) runs both, so a rule changed on one side only fails a test.
 *
 * Like the other parsers they collect every problem with a path, ignore unknown keys inside
 * `data`, and return a fresh object built from the keys they know. Unlike the milestone-2 parsers
 * they re-check no statistic (ADR-0001, contract.md "What each reader checks (1.4.0)"): shapes,
 * types, closed enums, nulls, bounds, array lengths and integer bookkeeping only. z, the p-values
 * (from z or from each test's statistic), the intervals, the information criteria, the root
 * moduli, the cancelling rule, the llf gap, the verdicts and every ACF `outside` flag are Python's,
 * checked by Python's validators alone; the app draws them as exported.
 *
 * In its own module so that only the fit page bundles it.
 */
import { capped, isRecord, MAX_LIST, MAX_NAMES, tooMany, typeName } from './contract'
import { MISSING, Reader, shown } from './contract.reader'

export const MODEL_IDS = ['aic', 'bic', 'course'] as const
export type ModelId = (typeof MODEL_IDS)[number]
/** The primary model: the AIC choice (owner's default, LEARNING_LOG); payloads.PRIMARY. */
export const PRIMARY = 'aic' as const
export const SERIAL_VERDICTS = ['found', 'not_found', 'not_tested'] as const
export type SerialVerdict = (typeof SERIAL_VERDICTS)[number]
export const NORMALITY_VERDICTS = ['rejected', 'not_rejected'] as const
export type NormalityVerdict = (typeof NORMALITY_VERDICTS)[number]
export const ARCH_VERDICTS = ['found', 'not_found'] as const
export type ArchVerdict = (typeof ARCH_VERDICTS)[number]
// The same codes as contract.order.ts, restated so that this chunk does not pull that module in.
const TREND_CODES = ['c', 'n', 't'] as const
export type TrendCode = (typeof TREND_CODES)[number]

/** z for alpha 0.05, the literal both readers hold (payloads.Z_FOR_ALPHA; contract.order.ts has the same double). */
export const Z95 = 1.959963984540054
const FIT_FLAGS = ['enforce_stationarity', 'enforce_invertibility', 'concentrate_scale'] as const
const INFERENCE = ['std_err', 'z', 'p_value', 'ci_low', 'ci_high'] as const
/**
 * The largest p and q, and d, a fit file may state (payloads.MAX_PQ and MAX_D), checked before any
 * list is built from them: an order of 2 ** 32 must give one short error, not a RangeError. The
 * burn-in is d for these models, so it has the same bound as d.
 */
export const MAX_PQ = 10
export const MAX_D = 2
/** p + q coefficients, a trend term and sigma2: the most parameters a bounded order has (payloads.MAX_FIT_PARAMS). */
const MAX_FIT_PARAMS = 2 * MAX_PQ + 2
/**
 * The refit's log-likelihood tolerance and the cancelling distance (fitting.LLF_TOLERANCE and
 * fitting.CANCEL_DISTANCE; payloads.LLF_TOLERANCE and payloads.CANCEL_DISTANCE), pinned, never read
 * from the file: a file that states another value is refused, as with NESTING_TOLERANCE.
 */
export const LLF_TOLERANCE = 1e-6
export const CANCEL_DISTANCE = 0.1
/**
 * The residual tests' settings (diagnostics.ALPHA, LJUNG_BOX_LAGS, ARCH_LM_LAGS, NLAGS and the ddof the
 * exporter gives het_arch; payloads.ALPHA and the others), pinned the same way. The lags decide which
 * rows exist, hence the verdicts, so a file that stated others (a Ljung-Box at lag 5 alone) could change
 * a verdict and still agree with itself; it is refused instead.
 */
export const ALPHA = 0.05
export const LJUNG_BOX_LAGS: readonly number[] = [5, 10, 20]
export const ARCH_LM_LAGS: readonly number[] = [5, 10]
export const ARCH_LM_DDOF = 0
export const NLAGS = 50
/** The most warnings one fit's list may hold (payloads.MAX_WARNINGS), checked before the list is read. */
export const MAX_WARNINGS = 100
/** statsmodels 0.15.0 labels ARIMA's drift as an exogenous "x1" (payloads.LIBRARY_NAMES). */
const LIBRARY_NAMES: ReadonlyMap<string, string> = new Map([['drift', 'x1']])

type Triple = [number, number, number]

export interface FitParam {
  name: string
  library_name: string
  value: number
  /**
   * The five inference fields are null together (a singular covariance). sigma2's z and p_value are
   * always null: its null value 0 is on the boundary, where the z-test does not apply.
   */
  std_err: number | null
  z: number | null
  p_value: number | null
  ci_low: number | null
  ci_high: number | null
}

export interface InvRoot {
  re: number
  im: number
  modulus: number
}

/** Indices into inv_roots_ar and inv_roots_ma: Python's pairing, drawn as exported. */
export interface CancellingPair {
  ar: number
  ma: number
  distance: number
}

export interface LjungBoxRow {
  lag: number
  model_df: number
  /** lag - model_df, and the p-value: null exactly when the test is not applied (lag <= p + q). */
  df: number | null
  statistic: number
  p_value: number | null
  applied: boolean
}

export interface Diagnostics {
  n: number
  burn_excluded: number
  burned: { date: string; resid: number; resid_std: number }[]
  max_abs_resid_after_burn: number
  ljung_box: LjungBoxRow[]
  jarque_bera: { statistic: number; p_value: number; skew: number; kurtosis: number }
  arch_lm: { lags: number; statistic: number; p_value: number }[]
  /** Python's rejections at alpha. The app keys fixed text by these; it never compares a p-value. */
  verdicts: { serial_correlation: SerialVerdict; normality: NormalityVerdict; arch: ArchVerdict }
  acf_outside_count: number
  acf_squared_outside_count: number
}

export interface Warning {
  category: string
  message: string
}

export interface FitModel {
  id: ModelId
  label: string
  source: string
  order: Triple
  trend: TrendCode
  nobs: number
  nobs_effective: number
  loglikelihood_burn: number
  params: FitParam[]
  information: { llf: number; aic: number; aicc: number; bic: number; hqic: number }
  /** Null exactly for the course model, which is not a grid cell. */
  grid_llf: number | null
  llf_gap: number | null
  converged: boolean
  iterations: number
  warnflag: number
  warnings: Warning[]
  inv_roots_ar: InvRoot[]
  inv_roots_ma: InvRoot[]
  cancelling_pairs: CancellingPair[]
  diagnostics: Diagnostics
}

export interface CourseTrack {
  pmdarima_version: string
  n_course: number
  n_train: number
  test_rows_seen: number
  full_series: { order: Triple; with_intercept: boolean; trend: TrendCode | null; aic: number; nobs: number; params: { name: string; value: number }[]; warnings: Warning[] }
  train_only: { order: Triple; with_intercept: boolean; trend: TrendCode | null } | null
  same_order: boolean | null
  refit_trend: TrendCode
  drift_dropped: {
    selected_trend: TrendCode | null
    refit_trend: TrendCode
    aic_without_drift: number
    aic_with_drift: number
    aic_gap: number
    drift: number
    drift_std_err: number | null
    drift_p_value: number | null
  }
}

export interface Fit {
  sample: 'train'
  n_train: number
  primary: typeof PRIMARY
  fit_settings: {
    library: string
    version: string
    model: 'ARIMA'
    method: 'statespace'
    optimizer: string
    maxiter: number
    cov_type: 'opg'
    enforce_stationarity: boolean
    enforce_invertibility: boolean
    concentrate_scale: boolean
  }
  z95: number
  cancel_distance: number
  llf_tolerance: number
  diagnostic_settings: { alpha: number; series: string; ljung_box_lags: number[]; ljung_box_model_df: string; arch_lm_lags: number[]; arch_lm_ddof: number; nlags: number }
  /** Exactly three, in the order of MODEL_IDS. */
  models: FitModel[]
  course_track: CourseTrack
  clustering_prediction: { model_id: ModelId; confirmed: boolean; arch_lm_rejections: number; acf_squared_outside_count: number; acf_squared_expected_by_chance: number }
}

export interface ResidualCorrelogram {
  band: number
  outside_count: number
  /** `outside` is Python's |acf| > band at that lag; the app draws the flag and never recomputes it. */
  rows: { lag: number; acf: number; outside: boolean }[]
}

export interface Residuals {
  sample: 'train'
  model_id: ModelId
  n: number
  burn_excluded: number
  z: number
  nlags: number
  rows: { date: string; resid_std: number }[]
  acf: ResidualCorrelogram
  acf_squared: ResidualCorrelogram
  qq: { theoretical: number; t_theoretical: number; sample: number }[]
  t_fit: { df: number; loc: number; scale: number }
}

export type FitResult = { ok: true; fit: Fit } | { ok: false; errors: string[] }
export type ResidualsResult = { ok: true; residuals: Residuals } | { ok: false; errors: string[] }

// Messages quote values through `shown`, so a value of any size gives a short message.
const show = shown

/** Our parameter names in statsmodels' order: the trend term, the AR lags, the MA lags, sigma2. */
export function expectedParamNames(p: number, q: number, trend: TrendCode): string[] {
  const lead = { n: [], c: ['const'], t: ['drift'] }[trend]
  return [...lead, ...Array.from({ length: p }, (_, i) => `ar.L${i + 1}`), ...Array.from({ length: q }, (_, i) => `ma.L${i + 1}`), 'sigma2']
}

/**
 * `value` when the sub-parser that built it recorded no new problem. Every Reader method records a
 * problem when it returns undefined (field() records a missing key), so then no field is undefined;
 * the second test makes sure of it.
 */
function clean<T>(r: Reader, start: number, value: { [K in keyof T]: T[K] | undefined }): T | undefined {
  return r.errors.length === start && Object.values(value).every((x) => x !== undefined) ? (value as T) : undefined
}

function sameValues(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i])
}

/** The object at `o[key]`, or undefined (a missing key is recorded once, by field()). */
function objAt(r: Reader, o: Record<string, unknown>, key: string, at: string): Record<string, unknown> | undefined {
  const v = r.field(o, key, at)
  return v === MISSING ? undefined : r.obj(v, `${at}.${key}`)
}

/** An object of finite numbers under `keys`. */
function numbers<K extends string>(r: Reader, v: unknown, at: string, keys: readonly K[]): Record<K, number> | undefined {
  if (v === MISSING) return undefined
  const o = r.obj(v, at)
  if (!o) return undefined
  const start = r.errors.length
  const out = Object.fromEntries(keys.map((k) => [k, r.num(r.field(o, k, at), `${at}.${k}`)])) as Record<K, number | undefined>
  return clean<Record<K, number>>(r, start, out)
}

/** A probability: a finite number in [0, 1] (a range check on the exported value, not a test). */
function pValue(r: Reader, v: unknown, at: string): number | undefined {
  const p = r.num(v, at)
  if (p !== undefined && !(p >= 0 && p <= 1)) {
    r.errors.push(`${at}: must be between 0 and 1, got ${p}`)
    return undefined
  }
  return p
}

function pValueOrNull(r: Reader, v: unknown, at: string): number | null | undefined {
  return v === null ? null : pValue(r, v, at)
}

/** An integer from 0 to `most`, or one short error. */
function bounded(r: Reader, v: unknown, at: string, most: number): number | undefined {
  const x = r.int(v, at)
  if (x !== undefined && x > most) {
    r.errors.push(`${at}: expected an integer from 0 to ${most}, got ${x}`)
    return undefined
  }
  return x
}

/** [p, d, q] with p and q at most MAX_PQ and d at most MAX_D, checked before anything is built from it. */
function parseOrder(r: Reader, v: unknown, at: string): Triple | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  if (list.length !== 3) {
    r.errors.push(`${at}: expected [p, d, q], got ${show(list)}`)
    return undefined
  }
  const out = list.map((x, i) => bounded(r, x, `${at}[${i}]`, i === 1 ? MAX_D : MAX_PQ))
  return out.every((x) => x !== undefined) ? (out as Triple) : undefined
}

/** statsmodels' ARIMA default trend: 'c' without differencing, 'n' with it (payloads._default_trend). */
export function defaultTrend(d: number): TrendCode {
  return d === 0 ? 'c' : 'n'
}

/** A non-empty, strictly ascending list of lags >= 1. */
function lagList(r: Reader, v: unknown, at: string): number[] | undefined {
  const list = r.list(v, at, MAX_NAMES, 'lags')
  if (!list) return undefined
  const out = list.map((x, i) => r.int(x, `${at}[${i}]`, 1))
  if (out.some((x) => x === undefined)) return undefined
  const values = out as number[]
  if (values.length === 0 || values.some((x, i) => i > 0 && x <= values[i - 1])) {
    r.errors.push(`${at}: must be a non-empty, strictly ascending list, got ${show(values)}`)
    return undefined
  }
  return values
}

/**
 * Every warning a fit raised, at most MAX_WARNINGS (payloads.MAX_WARNINGS): a longer list is one short
 * error, never a loop over it (3.3 million warnings once made 324 MB of messages).
 */
function warnings(r: Reader, v: unknown, at: string): Warning[] | undefined {
  const list = r.list(v, at, MAX_WARNINGS, 'warnings')
  if (!list) return undefined
  const start = r.errors.length
  const out = list.map((item, i) => {
    const w = r.obj(item, `${at}[${i}]`)
    if (!w) return undefined
    const [category, message] = (['category', 'message'] as const).map((k) => r.str(r.field(w, k, `${at}[${i}]`), `${at}[${i}].${k}`))
    return { category, message }
  })
  return r.errors.length === start ? (out as Warning[]) : undefined
}

/** One row per parameter, named as `names` says; the five inference fields all numbers or all null. */
function parseParams(r: Reader, v: unknown, at: string, names: string[] | undefined): FitParam[] | undefined {
  const rows = r.list(v, at, MAX_FIT_PARAMS, 'rows')
  if (!rows) return undefined
  if (names && rows.length !== names.length) r.errors.push(`${at}: has ${rows.length} rows, but the order and trend have ${names.length} parameters: ${names.join(', ')}`)
  const out: FitParam[] = []
  rows.forEach((item, i) => {
    const rat = `${at}[${i}]`
    const row = r.obj(item, rat)
    if (!row) return
    const start = r.errors.length
    const name = r.str(r.field(row, 'name', rat), `${rat}.name`)
    if (name !== undefined && names && i < names.length && name !== names[i]) r.errors.push(`${rat}.name: is ${show(name)}, expected ${show(names[i])}`)
    const library = r.str(r.field(row, 'library_name', rat), `${rat}.library_name`)
    const label = name === undefined ? undefined : (LIBRARY_NAMES.get(name) ?? name)
    if (library !== undefined && label !== undefined && library !== label) r.errors.push(`${rat}.library_name: is ${show(library)}; statsmodels labels ${show(name)} as ${show(label)}`)
    const value = r.num(r.field(row, 'value', rat), `${rat}.value`)
    const raw = INFERENCE.map((k) => r.field(row, k, rat))
    const nulls = INFERENCE.filter((_, k) => raw[k] === null)
    let inference: (number | null | undefined)[] = INFERENCE.map(() => null)
    // sigma2: std_err and the interval, never z or p (a boundary null); others: all five or none.
    const noTest = name === 'sigma2'
    if (nulls.length === INFERENCE.length) {
      // a singular covariance
    } else if (noTest && !sameValues(nulls, ['z', 'p_value'])) {
      r.errors.push(`${rat}: sigma2 has std_err and its interval, and z and p_value null (its null value 0 is on the boundary, where the z-test does not apply); got ${nulls.join(', ') || 'no'} null`)
    } else if (!noTest && nulls.length > 0) {
      r.errors.push(`${rat}: ${nulls.join(', ')} null but not all of ${INFERENCE.join(', ')}; they are null together`)
    } else {
      inference = INFERENCE.map((k, j) => (raw[j] === null ? null : k === 'p_value' ? pValue(r, raw[j], `${rat}.${k}`) : r.num(raw[j], `${rat}.${k}`)))
      const se = inference[0]
      if (se !== undefined && se !== null && se <= 0) r.errors.push(`${rat}.std_err: must be positive, got ${se}`)
    }
    const [std_err, z, p_value, ci_low, ci_high] = inference
    const param = clean<FitParam>(r, start, { name, library_name: library, value, std_err, z, p_value, ci_low, ci_high })
    if (param) out.push(param)
  })
  return out
}

/** Exactly `count` inverse roots. Their moduli and order are Python's to check. */
function parseRoots(r: Reader, v: unknown, at: string, count: number | undefined): InvRoot[] | undefined {
  const rows = r.arr(v, at)
  if (!rows) return undefined
  if (count !== undefined && rows.length !== count) {
    r.errors.push(`${at}: has ${rows.length} roots, expected ${count}`)
    return undefined
  }
  if (rows.length > MAX_PQ) {
    // No count (the order was refused): the list is bounded all the same (payloads._check_roots).
    r.errors.push(tooMany(at, rows.length, 'roots', MAX_PQ))
    return undefined
  }
  const out = rows.map((item, i) => numbers(r, item, `${at}[${i}]`, ['re', 'im', 'modulus'] as const))
  return out.every((x) => x !== undefined) ? (out as InvRoot[]) : undefined
}

/** Pairs of root indices, each in range and each used at most once. Which roots pair up is Python's rule. */
function parsePairs(r: Reader, v: unknown, at: string, ar: InvRoot[] | undefined, ma: InvRoot[] | undefined): CancellingPair[] | undefined {
  const rows = r.list(v, at, MAX_PQ, 'pairs') // one root of each kind per pair at most
  if (!rows) return undefined
  const start = r.errors.length
  const out: CancellingPair[] = []
  rows.forEach((item, k) => {
    const rat = `${at}[${k}]`
    const row = r.obj(item, rat)
    if (!row) return
    const i = r.int(r.field(row, 'ar', rat), `${rat}.ar`)
    const j = r.int(r.field(row, 'ma', rat), `${rat}.ma`)
    const distance = r.num(r.field(row, 'distance', rat), `${rat}.distance`)
    if (i === undefined || j === undefined || distance === undefined) return
    if (ar && ma && (i >= ar.length || j >= ma.length)) {
      r.errors.push(`${rat}: indices (${i}, ${j}) are out of range for ${ar.length} AR and ${ma.length} MA roots`)
      return
    }
    out.push({ ar: i, ma: j, distance })
  })
  if (new Set(out.map((p) => p.ar)).size !== out.length || new Set(out.map((p) => p.ma)).size !== out.length) r.errors.push(`${at}: a root appears in more than one pair`)
  return r.errors.length === start ? out : undefined
}

interface ModelFacts {
  burn: number | undefined
  nobs: number | undefined
  /** p + q, the Ljung-Box model_df. */
  pq: number | undefined
}

interface LagFacts {
  ljungBox: number[] | undefined
  archLm: number[] | undefined
}

function parseLjungBox(r: Reader, v: unknown, at: string, pq: number | undefined, lags: number[] | undefined): LjungBoxRow[] | undefined {
  const rows = r.list(v, at, LJUNG_BOX_LAGS.length, 'rows')
  if (!rows) return undefined
  if (lags && rows.length !== lags.length) r.errors.push(`${at}: has ${rows.length} rows, but ljung_box_lags has ${lags.length}`)
  const start = r.errors.length
  const out = rows.map((item, i) => {
    const rat = `${at}[${i}]`
    const row = r.obj(item, rat)
    if (!row) return undefined
    const lag = r.int(r.field(row, 'lag', rat), `${rat}.lag`, 1)
    if (lag !== undefined && lags && i < lags.length && lag !== lags[i]) r.errors.push(`${rat}.lag: is ${lag}, expected ${lags[i]}`)
    const mdf = r.int(r.field(row, 'model_df', rat), `${rat}.model_df`)
    if (mdf !== undefined && pq !== undefined && mdf !== pq) r.errors.push(`${rat}.model_df: is ${mdf}, but p + q is ${pq}`)
    const applied = r.bool(r.field(row, 'applied', rat), `${rat}.applied`)
    const statistic = r.num(r.field(row, 'statistic', rat), `${rat}.statistic`)
    const dfRaw = r.field(row, 'df', rat)
    const pRaw = r.field(row, 'p_value', rat)
    if (applied === undefined || lag === undefined || mdf === undefined) return undefined
    // Integer bookkeeping: the test has lag - model_df degrees of freedom, so it applies only past p + q.
    let df: number | null | undefined = null
    let p: number | null | undefined = null
    if (applied !== (lag > mdf)) r.errors.push(`${rat}.applied: is ${applied}, but the test applies exactly when lag ${lag} > model_df ${mdf}`)
    else if (applied) {
      df = r.int(dfRaw, `${rat}.df`, 1)
      if (df !== undefined && df !== lag - mdf) r.errors.push(`${rat}.df: is ${df}, but lag - model_df is ${lag - mdf}`)
      p = pValue(r, pRaw, `${rat}.p_value`)
    } else if (dfRaw !== null || pRaw !== null) r.errors.push(`${rat}: df and p_value must be null where the test is not applied`)
    return { lag, model_df: mdf, df, statistic, p_value: p, applied }
  })
  return r.errors.length === start ? (out as LjungBoxRow[]) : undefined
}

function parseArchLm(r: Reader, v: unknown, at: string, lags: number[] | undefined): Diagnostics['arch_lm'] | undefined {
  const rows = r.list(v, at, ARCH_LM_LAGS.length, 'rows')
  if (!rows) return undefined
  if (lags && rows.length !== lags.length) r.errors.push(`${at}: has ${rows.length} rows, but arch_lm_lags has ${lags.length}`)
  const start = r.errors.length
  const out = rows.map((item, i) => {
    const rat = `${at}[${i}]`
    const row = r.obj(item, rat)
    if (!row) return undefined
    const n = r.int(r.field(row, 'lags', rat), `${rat}.lags`, 1)
    if (n !== undefined && lags && i < lags.length && n !== lags[i]) r.errors.push(`${rat}.lags: is ${n}, expected ${lags[i]}`)
    return { lags: n, statistic: r.num(r.field(row, 'statistic', rat), `${rat}.statistic`), p_value: pValue(r, r.field(row, 'p_value', rat), `${rat}.p_value`) }
  })
  return r.errors.length === start ? (out as Diagnostics['arch_lm']) : undefined
}

function parseDiagnostics(r: Reader, v: unknown, at: string, facts: ModelFacts, lags: LagFacts): Diagnostics | undefined {
  if (v === MISSING) return undefined
  const dg = r.obj(v, at)
  if (!dg) return undefined
  const start = r.errors.length
  const n = r.int(r.field(dg, 'n', at), `${at}.n`, 2)
  const burn = bounded(r, r.field(dg, 'burn_excluded', at), `${at}.burn_excluded`, MAX_D)
  if (burn !== undefined && facts.burn !== undefined && burn !== facts.burn) r.errors.push(`${at}.burn_excluded: is ${burn}, but the fit's loglikelihood_burn is ${facts.burn}`)
  if (n !== undefined && burn !== undefined && facts.nobs !== undefined && n !== facts.nobs - burn) r.errors.push(`${at}.n: is ${n}, but nobs - burn_excluded is ${facts.nobs - burn}`)
  const burnedRaw = r.list(r.field(dg, 'burned', at), `${at}.burned`, MAX_D, 'rows') // burn_excluded is at most MAX_D
  let burned: Diagnostics['burned'] | undefined
  if (burnedRaw) {
    if (burn !== undefined && burnedRaw.length !== burn) r.errors.push(`${at}.burned: has ${burnedRaw.length} rows, but burn_excluded is ${burn}`)
    const bStart = r.errors.length
    const rows = burnedRaw.map((item, i) => {
      const bat = `${at}.burned[${i}]`
      const row = r.obj(item, bat)
      if (!row) return undefined
      return { date: r.date(r.field(row, 'date', bat), `${bat}.date`), resid: r.num(r.field(row, 'resid', bat), `${bat}.resid`), resid_std: r.num(r.field(row, 'resid_std', bat), `${bat}.resid_std`) }
    })
    if (r.errors.length === bStart) burned = rows as Diagnostics['burned']
  }
  let maxAbs = r.num(r.field(dg, 'max_abs_resid_after_burn', at), `${at}.max_abs_resid_after_burn`)
  if (maxAbs !== undefined && maxAbs < 0) {
    r.errors.push(`${at}.max_abs_resid_after_burn: must be >= 0, got ${maxAbs}`)
    maxAbs = undefined
  }
  const ljungBox = parseLjungBox(r, r.field(dg, 'ljung_box', at), `${at}.ljung_box`, facts.pq, lags.ljungBox)
  let jb = numbers(r, r.field(dg, 'jarque_bera', at), `${at}.jarque_bera`, ['statistic', 'p_value', 'skew', 'kurtosis'] as const)
  if (jb && pValue(r, jb.p_value, `${at}.jarque_bera.p_value`) === undefined) jb = undefined
  const archLm = parseArchLm(r, r.field(dg, 'arch_lm', at), `${at}.arch_lm`, lags.archLm)
  const vd = objAt(r, dg, 'verdicts', at)
  const verdicts = vd
    ? clean<Diagnostics['verdicts']>(r, r.errors.length, {
        serial_correlation: r.choice(r.field(vd, 'serial_correlation', `${at}.verdicts`), SERIAL_VERDICTS, `${at}.verdicts.serial_correlation`) ?? undefined,
        normality: r.choice(r.field(vd, 'normality', `${at}.verdicts`), NORMALITY_VERDICTS, `${at}.verdicts.normality`) ?? undefined,
        arch: r.choice(r.field(vd, 'arch', `${at}.verdicts`), ARCH_VERDICTS, `${at}.verdicts.arch`) ?? undefined,
      })
    : undefined
  const acfCount = r.int(r.field(dg, 'acf_outside_count', at), `${at}.acf_outside_count`)
  const acfSquaredCount = r.int(r.field(dg, 'acf_squared_outside_count', at), `${at}.acf_squared_outside_count`)
  return clean<Diagnostics>(r, start, {
    n,
    burn_excluded: burn,
    burned,
    max_abs_resid_after_burn: maxAbs,
    ljung_box: ljungBox,
    jarque_bera: jb,
    arch_lm: archLm,
    verdicts,
    acf_outside_count: acfCount,
    acf_squared_outside_count: acfSquaredCount,
  })
}

/** One model; its id, order and trend come back apart too, for the cross-checks below. */
function parseModel(r: Reader, item: unknown, at: string, nTrain: number | undefined, lags: LagFacts): { id?: ModelId; order?: Triple; trend?: TrendCode; model?: FitModel } {
  const m = r.obj(item, at)
  if (!m) return {}
  const start = r.errors.length
  const id = r.choice(r.field(m, 'id', at), MODEL_IDS, `${at}.id`) ?? undefined
  const label = r.str(r.field(m, 'label', at), `${at}.label`)
  const source = r.str(r.field(m, 'source', at), `${at}.source`)
  const order = parseOrder(r, r.field(m, 'order', at), `${at}.order`)
  const trend = r.choice(r.field(m, 'trend', at), TREND_CODES, `${at}.trend`) ?? undefined
  // An enum keyed by an integer: the course refits with statsmodels' default trend for its d.
  if (id === 'course' && order && trend && trend !== defaultTrend(order[1])) {
    r.errors.push(`${at}.trend: is ${show(trend)}, but ARIMA(train, order).fit() at d = ${order[1]} has statsmodels' default trend ${show(defaultTrend(order[1]))}`)
  }
  const nobs = r.int(r.field(m, 'nobs', at), `${at}.nobs`, 2)
  const eff = r.int(r.field(m, 'nobs_effective', at), `${at}.nobs_effective`, 1)
  const burn = bounded(r, r.field(m, 'loglikelihood_burn', at), `${at}.loglikelihood_burn`, MAX_D)
  if (nobs !== undefined && nTrain !== undefined && nobs !== nTrain) r.errors.push(`${at}.nobs: is ${nobs}, but n_train is ${nTrain}`)
  if (nobs !== undefined && eff !== undefined && burn !== undefined && eff !== nobs - burn) r.errors.push(`${at}.nobs_effective: is ${eff}, but nobs - loglikelihood_burn is ${nobs - burn}`)
  // Only from a bounded order: p of 2 ** 32 must not build 2 ** 32 names.
  const names = order && trend ? expectedParamNames(order[0], order[2], trend) : undefined
  const params = parseParams(r, r.field(m, 'params', at), `${at}.params`, names)
  const information = numbers(r, r.field(m, 'information', at), `${at}.information`, ['llf', 'aic', 'aicc', 'bic', 'hqic'] as const)
  const gridRaw = r.field(m, 'grid_llf', at)
  const gapRaw = r.field(m, 'llf_gap', at)
  const gridLlf = r.numOrNull(gridRaw, `${at}.grid_llf`)
  const llfGap = r.numOrNull(gapRaw, `${at}.llf_gap`)
  if (id && gridRaw !== MISSING && gapRaw !== MISSING && ((gridRaw === null) !== (id === 'course') || (gapRaw === null) !== (id === 'course'))) {
    r.errors.push(`${at}: grid_llf and llf_gap are null exactly for the course model, which is not a grid cell`)
  }
  const converged = r.bool(r.field(m, 'converged', at), `${at}.converged`)
  const iterations = r.int(r.field(m, 'iterations', at), `${at}.iterations`)
  const warnflag = r.int(r.field(m, 'warnflag', at), `${at}.warnflag`)
  const warns = warnings(r, r.field(m, 'warnings', at), `${at}.warnings`)
  const ar = parseRoots(r, r.field(m, 'inv_roots_ar', at), `${at}.inv_roots_ar`, order?.[0])
  const ma = parseRoots(r, r.field(m, 'inv_roots_ma', at), `${at}.inv_roots_ma`, order?.[2])
  const pairs = parsePairs(r, r.field(m, 'cancelling_pairs', at), `${at}.cancelling_pairs`, ar, ma)
  const facts = { burn, nobs, pq: order ? order[0] + order[2] : undefined }
  const diagnostics = parseDiagnostics(r, r.field(m, 'diagnostics', at), `${at}.diagnostics`, facts, lags)
  const model = clean<FitModel>(r, start, {
    id,
    label,
    source,
    order,
    trend,
    nobs,
    nobs_effective: eff,
    loglikelihood_burn: burn,
    params,
    information,
    grid_llf: gridLlf,
    llf_gap: llfGap,
    converged,
    iterations,
    warnflag,
    warnings: warns,
    inv_roots_ar: ar,
    inv_roots_ma: ma,
    cancelling_pairs: pairs,
    diagnostics,
  })
  return { id, order, trend, model }
}

function parseCourseTrack(r: Reader, v: unknown, nTrain: number | undefined, course: { order?: Triple; trend?: TrendCode } | undefined): CourseTrack | undefined {
  const at = 'data.course_track'
  if (v === MISSING) return undefined
  const t = r.obj(v, at)
  if (!t) return undefined
  const start = r.errors.length
  objAt(r, t, 'settings', at)
  const version = r.str(r.field(t, 'pmdarima_version', at), `${at}.pmdarima_version`)
  const nCourse = r.int(r.field(t, 'n_course', at), `${at}.n_course`, 2)
  const nt = r.int(r.field(t, 'n_train', at), `${at}.n_train`, 2)
  const seen = r.int(r.field(t, 'test_rows_seen', at), `${at}.test_rows_seen`)
  if (nt !== undefined && nTrain !== undefined && nt !== nTrain) r.errors.push(`${at}.n_train: is ${nt}, but data.n_train is ${nTrain}`)
  if (nCourse !== undefined && nt !== undefined && seen !== undefined && seen !== nCourse - nt) r.errors.push(`${at}.test_rows_seen: is ${seen}, but n_course - n_train is ${nCourse - nt}`)

  const fat = `${at}.full_series`
  const f = objAt(r, t, 'full_series', at)
  let full: CourseTrack['full_series'] | undefined
  if (f) {
    const fStart = r.errors.length
    const order = parseOrder(r, r.field(f, 'order', fat), `${fat}.order`)
    if (order && course?.order && !sameValues(order, course.order)) r.errors.push(`${fat}.order: is ${show(order)}, but the course model's order is ${show(course.order)}`)
    const nobs = r.int(r.field(f, 'nobs', fat), `${fat}.nobs`, 2)
    if (nobs !== undefined && nCourse !== undefined && nobs !== nCourse) r.errors.push(`${fat}.nobs: is ${nobs}, but n_course is ${nCourse}`)
    const paramsRaw = r.list(r.field(f, 'params', fat), `${fat}.params`, MAX_FIT_PARAMS, 'rows')
    const params = paramsRaw?.map((item, i) => {
      const pat = `${fat}.params[${i}]`
      const row = r.obj(item, pat)
      return row ? { name: r.str(r.field(row, 'name', pat), `${pat}.name`), value: r.num(r.field(row, 'value', pat), `${pat}.value`) } : undefined
    })
    full = clean<CourseTrack['full_series']>(r, fStart, {
      order,
      with_intercept: r.bool(r.field(f, 'with_intercept', fat), `${fat}.with_intercept`),
      trend: r.choice(r.field(f, 'trend', fat), TREND_CODES, `${fat}.trend`, true),
      aic: r.num(r.field(f, 'aic', fat), `${fat}.aic`),
      nobs,
      params: params as CourseTrack['full_series']['params'] | undefined,
      warnings: warnings(r, r.field(f, 'warnings', fat), `${fat}.warnings`),
    })
  }

  const trRaw = r.field(t, 'train_only', at)
  let trainOnly: CourseTrack['train_only'] | undefined = null
  if (trRaw !== null && trRaw !== MISSING) {
    const tr = r.obj(trRaw, `${at}.train_only`)
    trainOnly = tr
      ? clean<NonNullable<CourseTrack['train_only']>>(r, r.errors.length, {
          order: parseOrder(r, r.field(tr, 'order', `${at}.train_only`), `${at}.train_only.order`),
          with_intercept: r.bool(r.field(tr, 'with_intercept', `${at}.train_only`), `${at}.train_only.with_intercept`),
          trend: r.choice(r.field(tr, 'trend', `${at}.train_only`), TREND_CODES, `${at}.train_only.trend`, true),
        })
      : undefined
  }
  const sameRaw = r.field(t, 'same_order', at)
  let same: boolean | null | undefined
  if (sameRaw !== MISSING) {
    if ((sameRaw === null) !== (trRaw === null)) r.errors.push(`${at}.same_order: is null exactly when train_only is null`)
    else if (sameRaw === null) same = null
    else {
      same = r.bool(sameRaw, `${at}.same_order`)
      // Integer and boolean equality: the two searches chose the same (p, d, q) and the same intercept.
      if (same !== undefined && trainOnly && full && same !== (sameValues(trainOnly.order, full.order) && trainOnly.with_intercept === full.with_intercept)) {
        r.errors.push(`${at}.same_order: is ${same}, but the two searches chose ${show([trainOnly.order, trainOnly.with_intercept])} and ${show([full.order, full.with_intercept])}`)
      }
    }
  }
  const refit = r.choice(r.field(t, 'refit_trend', at), TREND_CODES, `${at}.refit_trend`) ?? undefined
  if (refit && course?.trend && refit !== course.trend) r.errors.push(`${at}.refit_trend: is ${show(refit)}, but the course model's trend is ${show(course.trend)}`)

  const dat = `${at}.drift_dropped`
  const d = objAt(r, t, 'drift_dropped', at)
  let drift: CourseTrack['drift_dropped'] | undefined
  if (d) {
    const dStart = r.errors.length
    const refit2 = r.choice(r.field(d, 'refit_trend', dat), TREND_CODES, `${dat}.refit_trend`) ?? undefined
    if (refit2 && refit && refit2 !== refit) r.errors.push(`${dat}.refit_trend: is ${show(refit2)}, but refit_trend is ${show(refit)}`)
    const selected = r.choice(r.field(d, 'selected_trend', dat), TREND_CODES, `${dat}.selected_trend`, true)
    // The search's own choice: full_series.trend (both nullable; an enum equality).
    if (selected !== undefined && full && selected !== full.trend) r.errors.push(`${dat}.selected_trend: is ${show(selected)}, but full_series.trend, the trend the search selected, is ${show(full.trend)}`)
    const seRaw = r.field(d, 'drift_std_err', dat)
    const pRaw = r.field(d, 'drift_p_value', dat)
    const se = r.numOrNull(seRaw, `${dat}.drift_std_err`)
    const p = pValueOrNull(r, pRaw, `${dat}.drift_p_value`)
    if (seRaw !== MISSING && pRaw !== MISSING && (seRaw === null) !== (pRaw === null)) r.errors.push(`${dat}: drift_std_err and drift_p_value are null together (a singular covariance)`)
    else if (se !== undefined && se !== null && se <= 0) r.errors.push(`${dat}.drift_std_err: must be positive, got ${se}`)
    drift = clean<CourseTrack['drift_dropped']>(r, dStart, {
      selected_trend: selected,
      refit_trend: refit2,
      aic_without_drift: r.num(r.field(d, 'aic_without_drift', dat), `${dat}.aic_without_drift`),
      aic_with_drift: r.num(r.field(d, 'aic_with_drift', dat), `${dat}.aic_with_drift`),
      aic_gap: r.num(r.field(d, 'aic_gap', dat), `${dat}.aic_gap`),
      drift: r.num(r.field(d, 'drift', dat), `${dat}.drift`),
      drift_std_err: se,
      drift_p_value: p,
    })
  }
  return clean<CourseTrack>(r, start, {
    pmdarima_version: version,
    n_course: nCourse,
    n_train: nt,
    test_rows_seen: seen,
    full_series: full,
    train_only: trainOnly,
    same_order: same,
    refit_trend: refit,
    drift_dropped: drift,
  })
}

/** Validates the `data` payload of the `fit` artifact (contract.md section 3.7). */
export function parseFit(data: unknown): FitResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  return capped(r.errors, 'data', () => readFit(r, data))
}

/** parseFit's body, stopped by `capped` at MAX_PROBLEMS problems. */
function readFit(r: Reader, data: Record<string, unknown>): FitResult {
  const sample = r.literal(r.field(data, 'sample', 'data'), 'train', 'data.sample')
  const nTrain = r.int(r.field(data, 'n_train', 'data'), 'data.n_train', 2)
  const primary = r.literal(r.field(data, 'primary', 'data'), PRIMARY, 'data.primary')

  const fs = objAt(r, data, 'fit_settings', 'data')
  const fat = 'data.fit_settings'
  const fitSettings = fs
    ? clean<Fit['fit_settings']>(r, r.errors.length, {
        library: r.str(r.field(fs, 'library', fat), `${fat}.library`),
        version: r.str(r.field(fs, 'version', fat), `${fat}.version`),
        model: r.literal(r.field(fs, 'model', fat), 'ARIMA', `${fat}.model`),
        method: r.literal(r.field(fs, 'method', fat), 'statespace', `${fat}.method`),
        optimizer: r.str(r.field(fs, 'optimizer', fat), `${fat}.optimizer`),
        maxiter: r.int(r.field(fs, 'maxiter', fat), `${fat}.maxiter`, 1),
        cov_type: r.literal(r.field(fs, 'cov_type', fat), 'opg', `${fat}.cov_type`),
        ...(Object.fromEntries(FIT_FLAGS.map((k) => [k, r.bool(r.field(fs, k, fat), `${fat}.${k}`)])) as Record<(typeof FIT_FLAGS)[number], boolean | undefined>),
      })
    : undefined

  const z95 = r.num(r.field(data, 'z95', 'data'), 'data.z95')
  if (z95 !== undefined && z95 !== Z95) r.errors.push(`data.z95: is ${z95}, expected ${Z95}`)
  const pinned = (key: 'cancel_distance' | 'llf_tolerance', value: number, rule: string) => {
    const stated = r.num(r.field(data, key, 'data'), `data.${key}`)
    if (stated !== undefined && stated !== value) r.errors.push(`data.${key}: is ${stated}, but this reader ${rule} ${value}`)
    return value // the reader's own value, whatever the file says
  }
  const cancelDistance = pinned('cancel_distance', CANCEL_DISTANCE, 'pairs roots within')
  const llfTolerance = pinned('llf_tolerance', LLF_TOLERANCE, "checks the refit's llf at")

  const ds = objAt(r, data, 'diagnostic_settings', 'data')
  const sat = 'data.diagnostic_settings'
  // The reader's own lags, whatever the file says: the rows are checked against them (a stated list that differs is refused below).
  const lags: LagFacts = { ljungBox: [...LJUNG_BOX_LAGS], archLm: [...ARCH_LM_LAGS] }
  let settings: Fit['diagnostic_settings'] | undefined
  if (ds) {
    const sStart = r.errors.length
    // The reader's own value back when the file's was readable; a different stated value is one error.
    const pinNumber = (value: number | undefined, at: string, own: number, rule: string): number | undefined => {
      if (value !== undefined && value !== own) r.errors.push(`${at}: is ${value}, but this reader ${rule} ${own}`)
      return value === undefined ? undefined : own
    }
    const pinList = (value: number[] | undefined, at: string, own: readonly number[], rule: string): number[] | undefined => {
      if (value !== undefined && !sameValues(value, own)) r.errors.push(`${at}: is ${show(value)}, but this reader ${rule} ${show(own)}`)
      return value === undefined ? undefined : [...own]
    }
    settings = clean<Fit['diagnostic_settings']>(r, sStart, {
      alpha: pinNumber(r.num(r.field(ds, 'alpha', sat), `${sat}.alpha`), `${sat}.alpha`, ALPHA, 'tests at alpha'),
      series: r.str(r.field(ds, 'series', sat), `${sat}.series`),
      ljung_box_lags: pinList(lagList(r, r.field(ds, 'ljung_box_lags', sat), `${sat}.ljung_box_lags`), `${sat}.ljung_box_lags`, LJUNG_BOX_LAGS, 'checks Ljung-Box at lags'),
      ljung_box_model_df: r.str(r.field(ds, 'ljung_box_model_df', sat), `${sat}.ljung_box_model_df`),
      arch_lm_lags: pinList(lagList(r, r.field(ds, 'arch_lm_lags', sat), `${sat}.arch_lm_lags`), `${sat}.arch_lm_lags`, ARCH_LM_LAGS, 'checks ARCH-LM at lags'),
      arch_lm_ddof: pinNumber(r.int(r.field(ds, 'arch_lm_ddof', sat), `${sat}.arch_lm_ddof`), `${sat}.arch_lm_ddof`, ARCH_LM_DDOF, 'checks ARCH-LM with ddof'),
      nlags: pinNumber(r.int(r.field(ds, 'nlags', sat), `${sat}.nlags`, 1), `${sat}.nlags`, NLAGS, 'checks the correlograms at nlags'),
    })
  }

  const list = r.list(r.field(data, 'models', 'data'), 'data.models', MODEL_IDS.length, 'models')
  const models: (FitModel | undefined)[] = []
  const byId = new Map<ModelId, ReturnType<typeof parseModel>>()
  if (list) {
    const ids = list.map((m) => (isRecord(m) ? m.id : null))
    if (!sameValues(ids, MODEL_IDS)) r.errors.push(`data.models: ids are ${show(ids)}, expected ${show(MODEL_IDS)} in that order`)
    list.forEach((item, i) => {
      const parsed = parseModel(r, item, `data.models[${i}]`, nTrain, lags)
      models.push(parsed.model)
      if (parsed.id) byId.set(parsed.id, parsed)
    })
  }

  const courseTrack = parseCourseTrack(r, r.field(data, 'course_track', 'data'), nTrain, byId.get('course'))

  const cat = 'data.clustering_prediction'
  const cp = objAt(r, data, 'clustering_prediction', 'data')
  let clustering: Fit['clustering_prediction'] | undefined
  if (cp) {
    const cStart = r.errors.length
    const mid = r.choice(r.field(cp, 'model_id', cat), MODEL_IDS, `${cat}.model_id`) ?? undefined
    if (mid && primary && mid !== primary) r.errors.push(`${cat}.model_id: is ${show(mid)}, but the primary model is ${show(primary)}`)
    const confirmed = r.bool(r.field(cp, 'confirmed', cat), `${cat}.confirmed`)
    const outside = r.int(r.field(cp, 'acf_squared_outside_count', cat), `${cat}.acf_squared_outside_count`)
    // Equalities with that model's exported diagnostics only; the p-value counts are Python's to check.
    const diag = mid ? byId.get(mid)?.model?.diagnostics : undefined
    if (diag && confirmed !== undefined && confirmed !== (diag.verdicts.arch === 'found')) r.errors.push(`${cat}.confirmed: is ${confirmed}, but the model's ARCH verdict is ${show(diag.verdicts.arch)}`)
    if (diag && outside !== undefined && outside !== diag.acf_squared_outside_count) r.errors.push(`${cat}.acf_squared_outside_count: is ${outside}, but the model's diagnostics say ${diag.acf_squared_outside_count}`)
    clustering = clean<Fit['clustering_prediction']>(r, cStart, {
      model_id: mid,
      confirmed,
      arch_lm_rejections: r.int(r.field(cp, 'arch_lm_rejections', cat), `${cat}.arch_lm_rejections`),
      acf_squared_outside_count: outside,
      acf_squared_expected_by_chance: r.num(r.field(cp, 'acf_squared_expected_by_chance', cat), `${cat}.acf_squared_expected_by_chance`),
    })
  }

  const fit = clean<Fit>(r, 0, {
    sample,
    n_train: nTrain,
    primary,
    fit_settings: fitSettings,
    z95,
    cancel_distance: cancelDistance,
    llf_tolerance: llfTolerance,
    diagnostic_settings: settings,
    models: models.every((m) => m !== undefined) && list ? (models as FitModel[]) : undefined,
    course_track: courseTrack,
    clustering_prediction: clustering,
  })
  return fit ? { ok: true, fit } : { ok: false, errors: r.errors }
}

/** The ACF of one series: lags 1..nlags in order, each acf in [-1, 1], outside_count the flagged rows. */
function parseCorrelogram(r: Reader, v: unknown, at: string, nlags: number | undefined): ResidualCorrelogram | undefined {
  if (v === MISSING) return undefined
  const g = r.obj(v, at)
  if (!g) return undefined
  const start = r.errors.length
  const band = r.num(r.field(g, 'band', at), `${at}.band`)
  if (band !== undefined && band <= 0) r.errors.push(`${at}.band: must be positive, got ${band}`)
  const count = r.int(r.field(g, 'outside_count', at), `${at}.outside_count`)
  const rowsRaw = r.list(r.field(g, 'rows', at), `${at}.rows`, MAX_LIST, 'rows')
  if (!rowsRaw) return undefined
  if (nlags !== undefined && rowsRaw.length !== nlags) r.errors.push(`${at}.rows: has ${rowsRaw.length} rows, but lags 1 to ${nlags} make ${nlags}`)
  const flags: (boolean | undefined)[] = []
  const rows = rowsRaw.map((item, k) => {
    const rat = `${at}.rows[${k}]`
    const row = r.obj(item, rat)
    if (!row) {
      flags.push(undefined)
      return undefined
    }
    const lag = r.int(r.field(row, 'lag', rat), `${rat}.lag`, 1)
    if (lag !== undefined && lag !== k + 1) r.errors.push(`${rat}.lag: is ${lag}, expected ${k + 1}`)
    const acf = r.num(r.field(row, 'acf', rat), `${rat}.acf`)
    if (acf !== undefined && !(acf >= -1 && acf <= 1)) r.errors.push(`${rat}.acf: must be between -1 and 1, got ${acf}`)
    const outside = r.bool(r.field(row, 'outside', rat), `${rat}.outside`)
    flags.push(outside)
    return { lag, acf, outside }
  })
  // Counting the rows Python flagged is bookkeeping; whether a row is past its band is Python's call.
  if (count !== undefined && flags.every((f) => f !== undefined) && count !== flags.filter((f) => f).length) {
    r.errors.push(`${at}.outside_count: is ${count}, but ${flags.filter((f) => f).length} rows are flagged`)
  }
  return clean<ResidualCorrelogram>(r, start, { band, outside_count: count, rows: rows as ResidualCorrelogram['rows'] })
}

/** Validates the `data` payload of a `residuals_<modelId>` artifact (contract.md section 3.8). */
export function parseResiduals(data: unknown, modelId: ModelId): ResidualsResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  return capped(r.errors, 'data', () => readResiduals(r, data, modelId))
}

/** parseResiduals's body, stopped by `capped` at MAX_PROBLEMS problems. */
function readResiduals(r: Reader, data: Record<string, unknown>, modelId: ModelId): ResidualsResult {
  const sample = r.literal(r.field(data, 'sample', 'data'), 'train', 'data.sample')
  const id = r.literal(r.field(data, 'model_id', 'data'), modelId, 'data.model_id')
  const n = r.int(r.field(data, 'n', 'data'), 'data.n', 2)
  const burn = bounded(r, r.field(data, 'burn_excluded', 'data'), 'data.burn_excluded', MAX_D)
  const z = r.num(r.field(data, 'z', 'data'), 'data.z')
  if (z !== undefined && z !== Z95) r.errors.push(`data.z: is ${z}, expected ${Z95}`)
  const nlags = r.int(r.field(data, 'nlags', 'data'), 'data.nlags', 1)

  const rowsRaw = r.list(r.field(data, 'rows', 'data'), 'data.rows', MAX_LIST, 'rows')
  let rows: Residuals['rows'] | undefined
  if (rowsRaw) {
    if (n !== undefined && rowsRaw.length !== n) r.errors.push(`data.rows: has ${rowsRaw.length} rows, but n is ${n}`)
    const start = r.errors.length
    let previous: string | undefined
    const out = rowsRaw.map((item, i) => {
      const row = r.obj(item, `data.rows[${i}]`)
      if (!row) return undefined
      const date = r.date(r.field(row, 'date', `data.rows[${i}]`), `data.rows[${i}].date`)
      if (date !== undefined) {
        if (previous !== undefined && date <= previous) r.errors.push(`data.rows[${i}].date: ${date} does not come after ${previous}`)
        previous = date
      }
      return { date, resid_std: r.num(r.field(row, 'resid_std', `data.rows[${i}]`), `data.rows[${i}].resid_std`) }
    })
    if (r.errors.length === start) rows = out as Residuals['rows']
  }
  const acf = parseCorrelogram(r, r.field(data, 'acf', 'data'), 'data.acf', nlags)
  const acfSquared = parseCorrelogram(r, r.field(data, 'acf_squared', 'data'), 'data.acf_squared', nlags)

  const qqRaw = r.list(r.field(data, 'qq', 'data'), 'data.qq', MAX_LIST, 'points')
  let qq: Residuals['qq'] | undefined
  if (qqRaw) {
    if (n !== undefined && qqRaw.length !== n) r.errors.push(`data.qq: has ${qqRaw.length} points, but n is ${n}`)
    const out = qqRaw.map((item, i) => numbers(r, item, `data.qq[${i}]`, ['theoretical', 't_theoretical', 'sample'] as const))
    if (out.every((x) => x !== undefined)) qq = out as Residuals['qq']
  }
  let tFit = numbers(r, r.field(data, 't_fit', 'data'), 'data.t_fit', ['df', 'loc', 'scale'] as const)
  for (const k of ['df', 'scale'] as const) {
    if (tFit && tFit[k] <= 0) {
      r.errors.push(`data.t_fit.${k}: must be positive, got ${tFit[k]}`)
      tFit = undefined
    }
  }

  const residuals = clean<Residuals>(r, 0, { sample, model_id: id, n, burn_excluded: burn, z, nlags, rows, acf, acf_squared: acfSquared, qq, t_fit: tFit })
  return residuals ? { ok: true, residuals } : { ok: false, errors: r.errors }
}

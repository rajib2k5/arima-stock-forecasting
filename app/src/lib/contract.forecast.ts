/**
 * Payload parsers for the milestone-4 artifacts: the seven `forecast_<model>_<method>` files and
 * `evaluation` (contract.md sections 3.9 and 3.10). The Python copy of every rule is in
 * src/arima_forecasting/payloads.py (validate_forecast, validate_evaluation); the shared corpus
 * (src/test/fixtures/payload_cases.json) runs both, so a rule changed on one side only fails a test.
 *
 * Like the milestone-3 parsers they collect every problem with a path, ignore unknown keys inside
 * `data`, return a fresh object built from the keys they know, and re-check no number (ADR-0001,
 * contract.md "What each reader checks (1.5.0)"): shapes, types, closed enums, nulls, the pinned
 * settings, bounds, the row sets and their order, and integer and date bookkeeping only. The dollar
 * values, the t multipliers, every metric and ratio, the DM statistics and p-values, the coverage
 * rates and Kupiec tests, and every verdict a p-value decides are Python's, checked by Python's
 * validators alone; the app draws them as exported.
 *
 * Every count is bounded before anything is built from it: a window's n (MAX_ROWS) before its rows
 * are read, the order before parameter names are built, and a list of the wrong length (the refits,
 * a row set) gives one short error instead of a loop over it. Messages quote values through
 * `shown`, so no value makes a long one.
 *
 * In its own module so that only the forecast page bundles it. For the same reason it restates the
 * few facts of the fit module it needs (the model ids, the trend codes, the order bounds, the
 * parameter names) instead of importing contract.fit.ts; contract.forecast.test.ts ties the copies.
 */
import { capped, isRecord, typeName } from './contract'
import { MISSING, Reader, shown } from './contract.reader'

// As contract.fit.ts (MODEL_IDS, TREND_CODES, MAX_PQ, MAX_D), restated so that this chunk does not pull that module in.
export const MODEL_IDS = ['aic', 'bic', 'course'] as const
export type ModelId = (typeof MODEL_IDS)[number]
const TREND_CODES = ['c', 'n', 't'] as const
export type TrendCode = (typeof TREND_CODES)[number]
export const MAX_PQ = 10
export const MAX_D = 2

export const METHODS = ['static', 'walk_forward', 'refit'] as const
export type Method = (typeof METHODS)[number]
export const KIND_IDS = ['multi_step', 'one_step'] as const
export type Kind = (typeof KIND_IDS)[number]
/** A static path forecasts every horizon from one origin; the walk-forward methods one step at a time (forecasting.KINDS). */
export const KINDS: Readonly<Record<Method, Kind>> = { static: 'multi_step', walk_forward: 'one_step', refit: 'one_step' }
/** The seven forecast files, in this order everywhere (forecasting.FORECASTS): the refit runs on the primary model only. */
export const FORECASTS: readonly (readonly [ModelId, Method])[] = [
  ['aic', 'static'],
  ['aic', 'walk_forward'],
  ['aic', 'refit'],
  ['bic', 'static'],
  ['bic', 'walk_forward'],
  ['course', 'static'],
  ['course', 'walk_forward'],
]
export const WINDOW_IDS = ['test', 'oos'] as const
export type WindowId = (typeof WINDOW_IDS)[number]
const PARAMETERS = ['train', 'expanding_refit'] as const
type ParameterSource = (typeof PARAMETERS)[number]

/**
 * The settings both readers pin and never take from the file (forecasting.LEVELS, NORMAL_Z and
 * REFIT_EVERY, evaluation.ALPHA and the DM settings; payloads.py holds the same values). Each stated
 * value is compared exactly: a value 1e-12 away, or one ulp away, is another value and is refused.
 */
export const LEVELS: readonly number[] = [0.8, 0.95]
/** scipy's norm.ppf(0.9) and norm.ppf(0.975). */
export const NORMAL_Z: readonly number[] = [1.2815515655446004, 1.959963984540054]
export const REFIT_EVERY = 21
export const ALPHA = 0.05
export const HEADLINE_USD = 'median' as const
/** The Method picker's text, pinned per method id (evaluation.METHOD_LABELS; payloads.METHOD_LABELS): free text could say "refit every 5 days" beside a refit every 21. */
export const METHOD_LABELS: Readonly<Record<Method, string>> = {
  static: "Static multi-step (the course's)",
  walk_forward: 'Walk-forward one-step',
  refit: 'Walk-forward one-step, refit every 21 days',
}
/** The Model picker's text, pinned per model id (fitting.LABELS; payloads.MODEL_LABELS), as the method labels are: free text could swap two models' names. */
export const MODEL_LABELS: Readonly<Record<ModelId, string>> = {
  aic: 'AIC choice (ADR-0002)',
  bic: 'BIC choice',
  course: 'Course refit',
}
export const LOSSES = ['squared', 'absolute'] as const
export type Loss = (typeof LOSSES)[number]
export const DM_SETTINGS = {
  horizon: 1,
  errors: 'log',
  losses: LOSSES,
  correction: 'harvey_leybourne_newbold',
  alternative: 'two_sided',
  baseline: 'random_walk',
  /** Within this many log points of the random walk's on every day, a model's forecasts are the random walk's, and DM is not run. */
  same_tolerance: 1e-9,
} as const
/** The most rows a window may state (payloads.MAX_ROWS), checked before any row is read. */
export const MAX_ROWS = 10_000
/** The most warnings one refit's list may hold (payloads.MAX_WARNINGS; contract.fit.ts has the same bound). */
export const MAX_WARNINGS = 100

export const DISTRIBUTIONS = ['normal', 't'] as const
export type Distribution = (typeof DISTRIBUTIONS)[number]
/** "same_as_rw": the model's one-step forecasts are the random walk's (an ARIMA(0, 1, 0) without a drift is one), so there is nothing to test. */
export const DM_VERDICTS = ['beats_rw', 'no_difference', 'worse_than_rw', 'same_as_rw'] as const
export type DmVerdict = (typeof DM_VERDICTS)[number]
export const COVERAGE_VERDICTS = ['too_narrow', 'consistent', 'too_wide', 'not_tested'] as const
export type CoverageVerdict = (typeof COVERAGE_VERDICTS)[number]

const ROW_NUMBERS = [
  'actual_log',
  'actual_usd',
  'mean_log',
  'sd_log',
  'median_usd',
  'mean_usd',
  'lower_80_usd',
  'upper_80_usd',
  'lower_95_usd',
  'upper_95_usd',
  't_lower_80_usd',
  't_upper_80_usd',
  't_lower_95_usd',
  't_upper_95_usd',
] as const

type Triple = [number, number, number]

export interface ForecastRow {
  date: string
  actual_log: number
  actual_usd: number
  mean_log: number
  /** > 0: the forecast's standard deviation of the log price, given the parameters. */
  sd_log: number
  /** exp(mean_log): the median of the implied log-normal price, the course's "forecast". */
  median_usd: number
  /** exp(mean_log + sd_log² / 2): its mean. */
  mean_usd: number
  lower_80_usd: number
  upper_80_usd: number
  lower_95_usd: number
  upper_95_usd: number
  t_lower_80_usd: number
  t_upper_80_usd: number
  t_lower_95_usd: number
  t_upper_95_usd: number
}

export interface ForecastWindow {
  id: WindowId
  start: string
  end: string
  n: number
  /** The last day before the window: where a static path starts, and the random walk's first forecast. */
  origin: { date: string; log_close: number; close_usd: number }
  rows: ForecastRow[]
}

export interface Warning {
  category: string
  message: string
}

export interface Refit {
  /** The first forecast date these parameters serve. */
  start_date: string
  n_obs: number
  params: { name: string; value: number }[]
  llf: number
  converged: boolean
  iterations: number
  warnings: Warning[]
}

export interface Forecast {
  model_id: ModelId
  label: string
  method: Method
  kind: Kind
  order: Triple
  trend: TrendCode
  parameters: ParameterSource
  /** REFIT_EVERY for the refit method, null otherwise. */
  refit_every: number | null
  t_df: number
  intervals: { levels: number[]; normal_z: number[]; t_quantile: number[]; t_scale: number; t_multiplier: number[] }
  /** Exactly two, "test" then "oos". */
  windows: ForecastWindow[]
  /** Null except for the refit method. */
  refits: Refit[] | null
}

export interface EvaluationWindow {
  id: WindowId
  start: string
  end: string
  n: number
  origin_date: string
}

export interface EvaluationModel {
  id: ModelId
  label: string
  /** The model's methods in FORECASTS order: the refit for the primary model only. */
  methods: Method[]
  t_df: number
}

export interface RandomWalkRow {
  kind: Kind
  window: WindowId
  n: number
  log: { rmse: number; mae: number }
  usd: { rmse: number; mae: number; mape_pct: number }
}

export interface UsdMetrics {
  rmse: number
  mae: number
  mape_pct: number
}

export interface MetricsRow {
  model_id: ModelId
  method: Method
  window: WindowId
  n: number
  log: { rmse: number; mae: number }
  usd_median: UsdMetrics
  usd_mean: UsdMetrics
  /** Each metric over the random walk's of the same kind and window, divided in Python. */
  ratio_to_rw: { log: { rmse: number; mae: number }; usd_median: UsdMetrics; usd_mean: UsdMetrics }
  back_transform: { max_pct: number; mean_pct: number }
}

export interface DmRow {
  model_id: ModelId
  method: Method
  window: WindowId
  loss: Loss
  n: number
  /** The largest |model forecast − random-walk forecast| over the window, in log points. */
  max_forecast_gap: number
  mean_diff: number
  /** > 0 for a tested row; >= 0 where the verdict is "same_as_rw" (the differential is 0 or rounding noise). */
  var_diff: number
  /** The statistic, its HLN-corrected value and the p-value: null exactly where the verdict is "same_as_rw", which is not tested. */
  statistic: number | null
  hln_factor: number
  statistic_hln: number | null
  df: number
  p_value: number | null
  /** Python's reading of the test at alpha. The app keys fixed text by it; it never compares a p-value. */
  verdict: DmVerdict
}

export interface CoverageRow {
  model_id: ModelId
  method: Method
  window: WindowId
  distribution: Distribution
  level: number
  n: number
  inside: number
  rate: number
  /** Kupiec's LR and its p-value: null exactly for a static (multi_step) path, whose days are not independent. */
  lr: number | null
  p_value: number | null
  /** "not_tested" exactly for a static path; otherwise Python's reading of Kupiec's test at alpha. */
  verdict: CoverageVerdict
}

export interface Evaluation {
  alpha: number
  interval_levels: number[]
  refit_every: number
  headline_usd: typeof HEADLINE_USD
  dm_settings: { horizon: number; errors: 'log'; losses: Loss[]; correction: string; alternative: string; baseline: string; same_tolerance: number }
  windows: EvaluationWindow[]
  models: EvaluationModel[]
  methods: { id: Method; kind: Kind; label: string }[]
  random_walk: RandomWalkRow[]
  metrics: MetricsRow[]
  dm: DmRow[]
  coverage: CoverageRow[]
}

export type ForecastResult = { ok: true; forecast: Forecast } | { ok: false; errors: string[] }
export type EvaluationResult = { ok: true; evaluation: Evaluation } | { ok: false; errors: string[] }

/** The artifact (and file stem) of a model's forecast by one method. */
export function artifactName(model: ModelId, method: Method): string {
  return `forecast_${model}_${method}`
}

/** A model's methods, in FORECASTS order. */
export function methodsOf(model: ModelId): Method[] {
  return FORECASTS.filter(([m]) => m === model).map(([, method]) => method)
}

export function hasForecast(model: string, method: string): boolean {
  return FORECASTS.some(([m, meth]) => m === model && meth === method)
}

/**
 * How many re-estimations a refit file lists for windows of these lengths: the first REFIT_EVERY of
 * the test and oos rows taken together use the training parameters, and each entry serves the next
 * REFIT_EVERY (integer bookkeeping, as contract.md section 3.9 states it).
 */
export function expectedRefits(nTest: number, nOos: number): number {
  return Math.ceil((nTest + nOos) / REFIT_EVERY) - 1
}

/** Our parameter names in statsmodels' order: the trend term, the AR lags, the MA lags, sigma2 (as contract.fit.ts's expectedParamNames). */
export function paramNames(p: number, q: number, trend: TrendCode): string[] {
  const lead = { n: [], c: ['const'], t: ['drift'] }[trend]
  return [...lead, ...Array.from({ length: p }, (_, i) => `ar.L${i + 1}`), ...Array.from({ length: q }, (_, i) => `ma.L${i + 1}`), 'sigma2']
}

// ---- small readers, as in contract.fit.ts ----

/** `value` when the sub-parser that built it recorded no new problem (every Reader method records one when it returns undefined). */
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

/** A finite number above `floor` (a bound on the exported value, not a test). */
function above(r: Reader, v: unknown, at: string, floor: number, why: string): number | undefined {
  const x = r.num(v, at)
  if (x !== undefined && !(x > floor)) {
    r.errors.push(`${at}: must be above ${floor} (${why}), got ${x}`)
    return undefined
  }
  return x
}

/** A finite number at least `floor`. */
function atLeast(r: Reader, v: unknown, at: string, floor: number, what: string): number | undefined {
  const x = r.num(v, at)
  if (x !== undefined && !(x >= floor)) {
    r.errors.push(`${at}: must be at least ${floor} (${what}), got ${x}`)
    return undefined
  }
  return x
}

/** A probability: a finite number in [0, 1]. */
function pValue(r: Reader, v: unknown, at: string): number | undefined {
  const p = r.num(v, at)
  if (p !== undefined && !(p >= 0 && p <= 1)) {
    r.errors.push(`${at}: must be between 0 and 1, got ${p}`)
    return undefined
  }
  return p
}

/** A row count from 1 to MAX_ROWS: checked before any row is read, so a stated 10⁹ never becomes a loop. */
function rowCount(r: Reader, v: unknown, at: string): number | undefined {
  if (v === MISSING) return undefined
  if (typeof v === 'number' && Number.isSafeInteger(v) && v >= 1 && v <= MAX_ROWS) return v
  r.errors.push(`${at}: expected an integer from 1 to ${MAX_ROWS}, got ${shown(v)}`)
  return undefined
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
    r.errors.push(`${at}: expected [p, d, q], got ${shown(list)}`)
    return undefined
  }
  const out = list.map((x, i) => bounded(r, x, `${at}[${i}]`, i === 1 ? MAX_D : MAX_PQ))
  return out.every((x) => x !== undefined) ? (out as Triple) : undefined
}

/** A pinned number: the file's value must be the reader's own, exactly. */
function pinNumber(r: Reader, value: number | undefined, at: string, own: number, rule: string): number | undefined {
  if (value !== undefined && value !== own) {
    r.errors.push(`${at}: is ${value}, but this reader ${rule} ${own}`)
    return undefined
  }
  return value
}

/** A pinned list: exactly the reader's own values, in order. A list of any other length is one short error. */
function pinList<T>(r: Reader, v: unknown, at: string, own: readonly T[], rule: string): T[] | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  if (!sameValues(list, own)) {
    r.errors.push(`${at}: is ${shown(list)}, but this reader ${rule} ${shown(own)}`)
    return undefined
  }
  return [...own]
}

/** Exactly `count` finite numbers. */
function numberList(r: Reader, v: unknown, at: string, count: number): number[] | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  if (list.length !== count) {
    r.errors.push(`${at}: expected ${count} numbers, got ${shown(list)}`)
    return undefined
  }
  const out = list.map((x, i) => r.num(x, `${at}[${i}]`))
  return out.every((x) => x !== undefined) ? (out as number[]) : undefined
}

/**
 * Every warning a fit raised, at most MAX_WARNINGS (payloads.MAX_WARNINGS): a longer list is one short
 * error, never a loop over it (3.3 million warnings once made 324 MB of messages).
 */
function warnings(r: Reader, v: unknown, at: string): Warning[] | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  if (list.length > MAX_WARNINGS) {
    r.errors.push(`${at}: has ${list.length} warnings, more than the ${MAX_WARNINGS} a reader takes`)
    return undefined
  }
  const start = r.errors.length
  const out = list.map((item, i) => {
    const w = r.obj(item, `${at}[${i}]`)
    if (!w) return undefined
    const [category, message] = (['category', 'message'] as const).map((k) => r.str(r.field(w, k, `${at}[${i}]`), `${at}[${i}].${k}`))
    return { category, message }
  })
  return r.errors.length === start && out.every((x) => x !== undefined) ? (out as Warning[]) : undefined
}

// ---- forecast_<model>_<method> ----

function parseRows(r: Reader, list: unknown[], at: string): ForecastRow[] | undefined {
  const start = r.errors.length
  let previous: string | undefined
  const out = list.map((item, i) => {
    const rat = `${at}[${i}]`
    const row = r.obj(item, rat)
    if (!row) return undefined
    const date = r.date(r.field(row, 'date', rat), `${rat}.date`)
    if (date !== undefined) {
      if (previous !== undefined && date <= previous) r.errors.push(`${rat}.date: ${date} does not come after ${previous}`)
      previous = date
    }
    const values = Object.fromEntries(ROW_NUMBERS.map((k) => [k, r.num(r.field(row, k, rat), `${rat}.${k}`)])) as Record<(typeof ROW_NUMBERS)[number], number | undefined>
    if (values.sd_log !== undefined && !(values.sd_log > 0)) r.errors.push(`${rat}.sd_log: must be above 0 (a forecast with no spread), got ${values.sd_log}`)
    return { date, ...values }
  })
  return r.errors.length === start && out.every((x) => x !== undefined) ? (out as ForecastRow[]) : undefined
}

interface WindowFacts {
  window?: ForecastWindow
  id?: WindowId
  start?: string
  end?: string
  n?: number
  /** The rows' dates, when every row parsed and there are exactly n of them. */
  dates?: string[]
}

function parseForecastWindow(r: Reader, item: unknown, at: string, expected: WindowId): WindowFacts {
  const w = r.obj(item, at)
  if (!w) return {}
  const start = r.errors.length
  const id = r.choice(r.field(w, 'id', at), WINDOW_IDS, `${at}.id`) ?? undefined
  if (id !== undefined && id !== expected) r.errors.push(`${at}.id: is ${shown(id)}, expected ${shown(expected)} (the windows are "test" then "oos")`)
  const first = r.date(r.field(w, 'start', at), `${at}.start`)
  const last = r.date(r.field(w, 'end', at), `${at}.end`)
  const n = rowCount(r, r.field(w, 'n', at), `${at}.n`)
  const oat = `${at}.origin`
  const o = objAt(r, w, 'origin', at)
  let origin: ForecastWindow['origin'] | undefined
  if (o) {
    const oStart = r.errors.length
    const date = r.date(r.field(o, 'date', oat), `${oat}.date`)
    if (date !== undefined && first !== undefined && !(date < first)) r.errors.push(`${oat}.date: is ${date}, but the origin is the last day before the window, which starts ${first}`)
    origin = clean<ForecastWindow['origin']>(r, oStart, { date, log_close: r.num(r.field(o, 'log_close', oat), `${oat}.log_close`), close_usd: r.num(r.field(o, 'close_usd', oat), `${oat}.close_usd`) })
  }
  const rowsRaw = r.field(w, 'rows', at)
  let rows: ForecastRow[] | undefined
  let dates: string[] | undefined
  // The bound first: no row is read when n is out of bounds, and no list longer than MAX_ROWS is walked.
  if (n !== undefined && rowsRaw !== MISSING) {
    const list = r.arr(rowsRaw, `${at}.rows`)
    if (list && list.length !== n) r.errors.push(`${at}.rows: has ${list.length} rows, but n is ${n}`)
    if (list && list.length <= MAX_ROWS) {
      rows = parseRows(r, list, `${at}.rows`)
      if (rows && rows.length > 0) {
        if (first !== undefined && rows[0].date !== first) r.errors.push(`${at}.rows[0].date: is ${rows[0].date}, but the window starts ${first}`)
        if (last !== undefined && rows[rows.length - 1].date !== last) r.errors.push(`${at}.rows[${rows.length - 1}].date: is ${rows[rows.length - 1].date}, but the window ends ${last}`)
      }
      if (rows && rows.length === n) dates = rows.map((row) => row.date)
    }
  }
  const window = clean<ForecastWindow>(r, start, { id, start: first, end: last, n, origin, rows })
  return { window, id, start: first, end: last, n, dates }
}

/** Exactly two windows, "test" then "oos", the test window ending before the oos window starts. */
function parseForecastWindows(r: Reader, v: unknown): { windows?: ForecastWindow[]; facts?: [WindowFacts, WindowFacts] } {
  const list = r.arr(v, 'data.windows')
  if (!list) return {}
  if (list.length !== WINDOW_IDS.length) {
    r.errors.push(`data.windows: has ${list.length} windows, expected 2: "test" then "oos"`)
    return {}
  }
  const facts = WINDOW_IDS.map((id, i) => parseForecastWindow(r, list[i], `data.windows[${i}]`, id)) as [WindowFacts, WindowFacts]
  const [test, oos] = facts
  if (test.id === 'test' && oos.id === 'oos' && test.end !== undefined && oos.start !== undefined && !(test.end < oos.start)) {
    r.errors.push(`data.windows[1].start: is ${oos.start}, but the test window ends ${test.end}; the oos window starts after it`)
  }
  const windows = facts.map((f) => f.window)
  return { windows: windows.every((w) => w !== undefined) ? (windows as ForecastWindow[]) : undefined, facts }
}

/** One {name, value} per parameter, named for the order and trend; built only from a bounded order. */
function parseRefitParams(r: Reader, v: unknown, at: string, names: string[] | undefined): Refit['params'] | undefined {
  const rows = r.arr(v, at)
  if (!rows || !names) return undefined
  if (rows.length !== names.length) {
    r.errors.push(`${at}: has ${rows.length} parameters, but the order and trend have ${names.length}: ${names.join(', ')}`)
    return undefined
  }
  const start = r.errors.length
  const out = rows.map((item, i) => {
    const pat = `${at}[${i}]`
    const row = r.obj(item, pat)
    if (!row) return undefined
    const name = r.str(r.field(row, 'name', pat), `${pat}.name`)
    if (name !== undefined && name !== names[i]) r.errors.push(`${pat}.name: is ${shown(name)}, expected ${shown(names[i])}`)
    return { name, value: r.num(r.field(row, 'value', pat), `${pat}.value`) }
  })
  return r.errors.length === start && out.every((x) => x !== undefined) ? (out as Refit['params']) : undefined
}

interface RefitFacts {
  /** The file's own method, when it is one. */
  method?: Method
  names?: string[]
  /** The test rows' dates followed by the oos rows'. */
  dates?: string[]
  expected?: number
}

function parseRefits(r: Reader, v: unknown, facts: RefitFacts): Refit[] | null | undefined {
  const at = 'data.refits'
  if (v === MISSING || facts.method === undefined) return undefined
  if (facts.method !== 'refit') {
    if (v !== null) r.errors.push(`${at}: must be null for method "${facts.method}", which keeps the training parameters`)
    return v === null ? null : undefined
  }
  if (v === null) {
    r.errors.push(`${at}: is null, but the refit method lists every re-estimation`)
    return undefined
  }
  const list = r.arr(v, at)
  if (!list || facts.expected === undefined) return undefined
  // One short error for a list of the wrong length, however long: never a loop over it.
  if (list.length !== facts.expected) {
    r.errors.push(`${at}: has ${list.length} entries, but the test and oos rows take ${facts.expected} (one per ${REFIT_EVERY} rows after the first ${REFIT_EVERY})`)
    return undefined
  }
  const start = r.errors.length
  let previous: number | undefined
  const out = list.map((item, k) => {
    const eat = `${at}[${k}]`
    const e = r.obj(item, eat)
    if (!e) {
      previous = undefined
      return undefined
    }
    const eStart = r.errors.length
    const date = r.date(r.field(e, 'start_date', eat), `${eat}.start_date`)
    // Entry k serves the rows from 21 (k + 1) on; the count above keeps that index inside the rows.
    const row = REFIT_EVERY * (k + 1)
    if (date !== undefined && facts.dates && date !== facts.dates[row]) r.errors.push(`${eat}.start_date: is ${date}, but row ${row} (from 0) of the test and oos rows is ${facts.dates[row]}`)
    const nObs = r.int(r.field(e, 'n_obs', eat), `${eat}.n_obs`, 1)
    if (nObs !== undefined && previous !== undefined && nObs !== previous + REFIT_EVERY) r.errors.push(`${eat}.n_obs: is ${nObs}, but the entry before was fitted on ${previous} observations and each refit adds ${REFIT_EVERY}`)
    previous = nObs
    return clean<Refit>(r, eStart, {
      start_date: date,
      n_obs: nObs,
      params: parseRefitParams(r, r.field(e, 'params', eat), `${eat}.params`, facts.names),
      llf: r.num(r.field(e, 'llf', eat), `${eat}.llf`),
      converged: r.bool(r.field(e, 'converged', eat), `${eat}.converged`),
      iterations: r.int(r.field(e, 'iterations', eat), `${eat}.iterations`),
      warnings: warnings(r, r.field(e, 'warnings', eat), `${eat}.warnings`),
    })
  })
  return r.errors.length === start && out.every((x) => x !== undefined) ? (out as Refit[]) : undefined
}

/** refit_every: REFIT_EVERY exactly for the refit method, null for the others. */
function parseRefitEvery(r: Reader, v: unknown, method: Method | undefined): number | null | undefined {
  const at = 'data.refit_every'
  if (v === MISSING || method === undefined) return undefined
  if (method !== 'refit') {
    if (v !== null) r.errors.push(`${at}: must be null for method "${method}", which does not re-estimate`)
    return v === null ? null : undefined
  }
  if (v === null) {
    r.errors.push(`${at}: is null, but the refit method re-estimates every ${REFIT_EVERY} rows`)
    return undefined
  }
  return pinNumber(r, r.int(v, at, 1), at, REFIT_EVERY, 're-estimates every')
}

/**
 * Validates the `data` payload of `forecast_<modelId>_<method>` (contract.md section 3.9). The caller
 * passes the model and method the file name gives; a payload that names others is refused, and so is
 * a pair for which no file is made.
 */
export function parseForecast(data: unknown, modelId: ModelId, method: Method): ForecastResult {
  if (!hasForecast(modelId, method)) {
    return { ok: false, errors: [`no forecast file is made for model ${shown(modelId)} and method ${shown(method)}; the files are ${FORECASTS.map(([m, meth]) => artifactName(m, meth)).join(', ')}`] }
  }
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  return capped(r.errors, 'data', () => readForecast(r, data, modelId, method))
}

/** parseForecast's body, stopped by `capped` at MAX_PROBLEMS problems. */
function readForecast(r: Reader, data: Record<string, unknown>, modelId: ModelId, method: Method): ForecastResult {
  const id = r.choice(r.field(data, 'model_id', 'data'), MODEL_IDS, 'data.model_id') ?? undefined
  if (id !== undefined && id !== modelId) r.errors.push(`data.model_id: is ${shown(id)}, but this is the file of model ${shown(modelId)}`)
  let label = r.str(r.field(data, 'label', 'data'), 'data.label')
  if (label !== undefined && label !== MODEL_LABELS[modelId]) {
    r.errors.push(`data.label: is ${shown(label)}, but this reader labels model ${shown(modelId)} ${shown(MODEL_LABELS[modelId])}`)
    label = undefined
  }
  // The file's own method decides kind, parameters, refit_every and refits; it must also be the file name's.
  const stated = r.choice(r.field(data, 'method', 'data'), METHODS, 'data.method') ?? undefined
  if (stated !== undefined && stated !== method) r.errors.push(`data.method: is ${shown(stated)}, but this is the file of method ${shown(method)}`)
  const kind = r.choice(r.field(data, 'kind', 'data'), KIND_IDS, 'data.kind') ?? undefined
  if (kind !== undefined && stated !== undefined && kind !== KINDS[stated]) r.errors.push(`data.kind: is ${shown(kind)}, but method ${shown(stated)} makes ${shown(KINDS[stated])} forecasts`)
  const order = parseOrder(r, r.field(data, 'order', 'data'), 'data.order')
  const trend = r.choice(r.field(data, 'trend', 'data'), TREND_CODES, 'data.trend') ?? undefined
  const parameters = r.choice(r.field(data, 'parameters', 'data'), PARAMETERS, 'data.parameters') ?? undefined
  if (parameters !== undefined && stated !== undefined) {
    const from: ParameterSource = stated === 'refit' ? 'expanding_refit' : 'train'
    if (parameters !== from) r.errors.push(`data.parameters: is ${shown(parameters)}, but method ${shown(stated)} takes its parameters from ${shown(from)}`)
  }
  const refitEvery = parseRefitEvery(r, r.field(data, 'refit_every', 'data'), stated)
  const tDf = above(r, r.field(data, 't_df', 'data'), 'data.t_df', 2, 'a Student-t on 2 or fewer degrees of freedom has no finite variance')

  const iat = 'data.intervals'
  const iv = objAt(r, data, 'intervals', 'data')
  let intervals: Forecast['intervals'] | undefined
  if (iv) {
    const iStart = r.errors.length
    intervals = clean<Forecast['intervals']>(r, iStart, {
      levels: pinList(r, r.field(iv, 'levels', iat), `${iat}.levels`, LEVELS, 'draws the intervals at levels'),
      normal_z: pinList(r, r.field(iv, 'normal_z', iat), `${iat}.normal_z`, NORMAL_Z, 'uses the normal quantiles'),
      t_quantile: numberList(r, r.field(iv, 't_quantile', iat), `${iat}.t_quantile`, LEVELS.length),
      t_scale: r.num(r.field(iv, 't_scale', iat), `${iat}.t_scale`),
      t_multiplier: numberList(r, r.field(iv, 't_multiplier', iat), `${iat}.t_multiplier`, LEVELS.length),
    })
  }

  const { windows, facts } = parseForecastWindows(r, r.field(data, 'windows', 'data'))
  const [test, oos]: [WindowFacts, WindowFacts] = facts ?? [{}, {}]
  const refits = parseRefits(r, r.field(data, 'refits', 'data'), {
    method: stated,
    // Only from a bounded order: p of 2 ** 32 must not build 2 ** 32 names.
    names: order && trend ? paramNames(order[0], order[2], trend) : undefined,
    dates: test.dates && oos.dates ? [...test.dates, ...oos.dates] : undefined,
    expected: test.n !== undefined && oos.n !== undefined ? expectedRefits(test.n, oos.n) : undefined,
  })

  const forecast = clean<Forecast>(r, 0, {
    model_id: id,
    label,
    method: stated,
    kind,
    order,
    trend,
    parameters,
    refit_every: refitEvery,
    t_df: tDf,
    intervals,
    windows,
    refits,
  })
  if (forecast) return { ok: true, forecast }
  return { ok: false, errors: r.errors.length > 0 ? r.errors : ['data: could not be read'] }
}

// ---- evaluation ----

const RW_KEYS: readonly (readonly [Kind, WindowId])[] = KIND_IDS.flatMap((k) => WINDOW_IDS.map((w) => [k, w] as const))
const METRIC_KEYS: readonly (readonly [ModelId, Method, WindowId])[] = FORECASTS.flatMap(([m, meth]) => WINDOW_IDS.map((w) => [m, meth, w] as const))
const DM_KEYS: readonly (readonly [ModelId, Method, WindowId, Loss])[] = FORECASTS.filter(([, meth]) => KINDS[meth] === 'one_step').flatMap(([m, meth]) =>
  WINDOW_IDS.flatMap((w) => LOSSES.map((loss) => [m, meth, w, loss] as const)),
)
const COVERAGE_KEYS: readonly (readonly [ModelId, Method, WindowId, Distribution, number])[] = FORECASTS.flatMap(([m, meth]) =>
  WINDOW_IDS.flatMap((w) => DISTRIBUTIONS.flatMap((dist) => LEVELS.map((_, i) => [m, meth, w, dist, i] as const))),
)

type WindowNs = Partial<Record<WindowId, number>>

/**
 * A list of exactly `keys.length` rows, each parsed with its expected key. A list of another length is
 * one short error and no row is read: a coverage list of a million rows costs one comparison.
 */
function rowSet<K, T>(r: Reader, v: unknown, at: string, keys: readonly K[], what: string, parse: (row: Record<string, unknown>, rat: string, key: K) => T | undefined): T[] | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  if (list.length !== keys.length) {
    r.errors.push(`${at}: has ${list.length} rows, expected ${keys.length}: ${what}`)
    return undefined
  }
  const start = r.errors.length
  const out = list.map((item, i) => {
    const row = r.obj(item, `${at}[${i}]`)
    return row ? parse(row, `${at}[${i}]`, keys[i]) : undefined
  })
  return r.errors.length === start && out.every((x) => x !== undefined) ? (out as T[]) : undefined
}

/** The row's key fields, read and compared with the key at its position as one tuple: one error per misplaced row. */
function keyFields<T extends readonly string[]>(r: Reader, row: Record<string, unknown>, rat: string, fields: readonly [string, readonly string[]][], expected: T): (string | undefined)[] {
  const got = fields.map(([name, options]) => r.choice(r.field(row, name, rat), options, `${rat}.${name}`) ?? undefined)
  if (got.every((x) => x !== undefined) && !sameValues(got, expected)) {
    r.errors.push(`${rat}: is the row of (${got.join(', ')}), but this position holds (${expected.join(', ')})`)
  }
  return got
}

/** A row's n: the n of its window. */
function windowN(r: Reader, v: unknown, at: string, window: WindowId | undefined, ns: WindowNs, min = 1): number | undefined {
  const n = r.int(v, at, min)
  const own = window === undefined ? undefined : ns[window]
  if (n !== undefined && own !== undefined && n !== own) {
    r.errors.push(`${at}: is ${n}, but the ${window} window has ${own} rows`)
    return undefined
  }
  return n
}

const LOG_KEYS = ['rmse', 'mae'] as const
/** The DM row's fields a test produces: null together exactly where the verdict is "same_as_rw". */
const TESTED = ['statistic', 'statistic_hln', 'p_value'] as const
const USD_KEYS = ['rmse', 'mae', 'mape_pct'] as const

function parseEvaluationWindows(r: Reader, v: unknown): { windows?: EvaluationWindow[]; ns: WindowNs } {
  const ns: WindowNs = {}
  const list = r.arr(v, 'data.windows')
  if (!list) return { ns }
  if (list.length !== WINDOW_IDS.length) {
    r.errors.push(`data.windows: has ${list.length} windows, expected 2: "test" then "oos"`)
    return { ns }
  }
  const out = WINDOW_IDS.map((expected, i) => {
    const at = `data.windows[${i}]`
    const w = r.obj(list[i], at)
    if (!w) return undefined
    const start = r.errors.length
    const id = r.choice(r.field(w, 'id', at), WINDOW_IDS, `${at}.id`) ?? undefined
    if (id !== undefined && id !== expected) r.errors.push(`${at}.id: is ${shown(id)}, expected ${shown(expected)} (the windows are "test" then "oos")`)
    const first = r.date(r.field(w, 'start', at), `${at}.start`)
    const last = r.date(r.field(w, 'end', at), `${at}.end`)
    if (first !== undefined && last !== undefined && first > last) r.errors.push(`${at}.end: is ${last}, before the window's start ${first}`)
    const n = rowCount(r, r.field(w, 'n', at), `${at}.n`)
    if (id === expected && n !== undefined) ns[expected] = n
    const origin = r.date(r.field(w, 'origin_date', at), `${at}.origin_date`)
    if (origin !== undefined && first !== undefined && !(origin < first)) r.errors.push(`${at}.origin_date: is ${origin}, but the origin is the last day before the window, which starts ${first}`)
    return clean<EvaluationWindow>(r, start, { id, start: first, end: last, n, origin_date: origin })
  })
  const [test, oos] = out
  if (test && oos && test.id === 'test' && oos.id === 'oos' && !(test.end < oos.start)) r.errors.push(`data.windows[1].start: is ${oos.start}, but the test window ends ${test.end}; the oos window starts after it`)
  return { windows: out.every((w) => w !== undefined) ? (out as EvaluationWindow[]) : undefined, ns }
}

function parseDmSettings(r: Reader, v: unknown): Evaluation['dm_settings'] | undefined {
  const at = 'data.dm_settings'
  if (v === MISSING) return undefined
  const s = r.obj(v, at)
  if (!s) return undefined
  const literal = <K extends 'errors' | 'correction' | 'alternative' | 'baseline'>(key: K) => r.literal(r.field(s, key, at), DM_SETTINGS[key], `${at}.${key}`)
  return clean<Evaluation['dm_settings']>(r, r.errors.length, {
    horizon: pinNumber(r, r.int(r.field(s, 'horizon', at), `${at}.horizon`, 1), `${at}.horizon`, DM_SETTINGS.horizon, 'tests one-step forecasts, horizon'),
    errors: literal('errors'),
    losses: pinList(r, r.field(s, 'losses', at), `${at}.losses`, DM_SETTINGS.losses, 'tests the losses'),
    correction: literal('correction'),
    alternative: literal('alternative'),
    baseline: literal('baseline'),
    same_tolerance: pinNumber(r, r.num(r.field(s, 'same_tolerance', at), `${at}.same_tolerance`), `${at}.same_tolerance`, DM_SETTINGS.same_tolerance, 'reads a model as the random walk within'),
  })
}

function parseModels(r: Reader, v: unknown): EvaluationModel[] | undefined {
  return rowSet(r, v, 'data.models', MODEL_IDS, '"aic", "bic", "course" in that order', (m, at, expected) => {
    const start = r.errors.length
    const id = r.choice(r.field(m, 'id', at), MODEL_IDS, `${at}.id`) ?? undefined
    if (id !== undefined && id !== expected) r.errors.push(`${at}.id: is ${shown(id)}, expected ${shown(expected)}`)
    // Against the row's own id when it is one, so a misplaced model is one error (its id), not two.
    const self = id ?? expected
    const methods = pinList(r, r.field(m, 'methods', at), `${at}.methods`, methodsOf(self), `lists model ${shown(self)}'s forecast files as`)
    let label = r.str(r.field(m, 'label', at), `${at}.label`)
    if (label !== undefined && label !== MODEL_LABELS[self]) {
      r.errors.push(`${at}.label: is ${shown(label)}, but this reader labels model ${shown(self)} ${shown(MODEL_LABELS[self])}`)
      label = undefined
    }
    return clean<EvaluationModel>(r, start, {
      id,
      label,
      methods,
      t_df: above(r, r.field(m, 't_df', at), `${at}.t_df`, 2, 'a Student-t on 2 or fewer degrees of freedom has no finite variance'),
    })
  })
}

function parseMethods(r: Reader, v: unknown): Evaluation['methods'] | undefined {
  return rowSet(r, v, 'data.methods', METHODS, '"static", "walk_forward", "refit" in that order', (m, at, expected) => {
    const start = r.errors.length
    const id = r.choice(r.field(m, 'id', at), METHODS, `${at}.id`) ?? undefined
    if (id !== undefined && id !== expected) r.errors.push(`${at}.id: is ${shown(id)}, expected ${shown(expected)}`)
    const kind = r.choice(r.field(m, 'kind', at), KIND_IDS, `${at}.kind`) ?? undefined
    const self = id ?? expected
    if (kind !== undefined && kind !== KINDS[self]) r.errors.push(`${at}.kind: is ${shown(kind)}, but method ${shown(self)} makes ${shown(KINDS[self])} forecasts`)
    let label = r.str(r.field(m, 'label', at), `${at}.label`)
    if (label !== undefined && label !== METHOD_LABELS[self]) {
      r.errors.push(`${at}.label: is ${shown(label)}, but this reader labels method ${shown(self)} ${shown(METHOD_LABELS[self])}`)
      label = undefined
    }
    return clean<Evaluation['methods'][number]>(r, start, { id, kind, label })
  })
}

function parseRandomWalk(r: Reader, v: unknown, ns: WindowNs): RandomWalkRow[] | undefined {
  return rowSet(r, v, 'data.random_walk', RW_KEYS, 'multi_step test, multi_step oos, one_step test, one_step oos', (row, at, key) => {
    const start = r.errors.length
    const [kind, window] = keyFields(r, row, at, [['kind', KIND_IDS], ['window', WINDOW_IDS]], key) as [Kind | undefined, WindowId | undefined]
    return clean<RandomWalkRow>(r, start, {
      kind,
      window,
      n: windowN(r, r.field(row, 'n', at), `${at}.n`, window, ns),
      log: numbers(r, r.field(row, 'log', at), `${at}.log`, LOG_KEYS),
      usd: numbers(r, r.field(row, 'usd', at), `${at}.usd`, USD_KEYS),
    })
  })
}

const FORECAST_KEY_FIELDS: readonly [string, readonly string[]][] = [
  ['model_id', MODEL_IDS],
  ['method', METHODS],
  ['window', WINDOW_IDS],
]

function parseMetrics(r: Reader, v: unknown, ns: WindowNs): MetricsRow[] | undefined {
  return rowSet(r, v, 'data.metrics', METRIC_KEYS, 'one per forecast file and window, in FORECASTS order, test before oos', (row, at, key) => {
    const start = r.errors.length
    const [model, method, window] = keyFields(r, row, at, FORECAST_KEY_FIELDS, key) as [ModelId | undefined, Method | undefined, WindowId | undefined]
    const rat = `${at}.ratio_to_rw`
    const ratios = objAt(r, row, 'ratio_to_rw', at)
    return clean<MetricsRow>(r, start, {
      model_id: model,
      method,
      window,
      n: windowN(r, r.field(row, 'n', at), `${at}.n`, window, ns),
      log: numbers(r, r.field(row, 'log', at), `${at}.log`, LOG_KEYS),
      usd_median: numbers(r, r.field(row, 'usd_median', at), `${at}.usd_median`, USD_KEYS),
      usd_mean: numbers(r, r.field(row, 'usd_mean', at), `${at}.usd_mean`, USD_KEYS),
      ratio_to_rw: ratios
        ? clean<MetricsRow['ratio_to_rw']>(r, r.errors.length, {
            log: numbers(r, r.field(ratios, 'log', rat), `${rat}.log`, LOG_KEYS),
            usd_median: numbers(r, r.field(ratios, 'usd_median', rat), `${rat}.usd_median`, USD_KEYS),
            usd_mean: numbers(r, r.field(ratios, 'usd_mean', rat), `${rat}.usd_mean`, USD_KEYS),
          })
        : undefined,
      back_transform: numbers(r, r.field(row, 'back_transform', at), `${at}.back_transform`, ['max_pct', 'mean_pct'] as const),
    })
  })
}

function parseDm(r: Reader, v: unknown, ns: WindowNs): DmRow[] | undefined {
  return rowSet(r, v, 'data.dm', DM_KEYS, 'one per one-step forecast file, window and loss (squared, then absolute)', (row, at, key) => {
    const start = r.errors.length
    const [model, method, window, loss] = keyFields(r, row, at, [...FORECAST_KEY_FIELDS, ['loss', LOSSES]], key) as [ModelId | undefined, Method | undefined, WindowId | undefined, Loss | undefined]
    // At least two forecasts: the variance of one loss differential is 0, and the t has n - 1 df.
    const n = windowN(r, r.field(row, 'n', at), `${at}.n`, window, ns, 2)
    const df = r.int(r.field(row, 'df', at), `${at}.df`)
    if (df !== undefined && n !== undefined && df !== n - 1) r.errors.push(`${at}.df: is ${df}, but n - 1 is ${n - 1}`)
    const verdict = r.choice(r.field(row, 'verdict', at), DM_VERDICTS, `${at}.verdict`) ?? undefined
    // The verdict fixes these: a model whose forecasts are the random walk's is not tested (Python decides which it is).
    const same = verdict === 'same_as_rw'
    const raw = TESTED.map((k) => r.field(row, k, at))
    let tested: (number | null | undefined)[] = TESTED.map(() => undefined)
    if (verdict !== undefined && raw.every((x) => x !== MISSING)) {
      const nulls = raw.filter((x) => x === null).length
      if (same && nulls !== TESTED.length) r.errors.push(`${at}: ${TESTED.join(', ')} must be null where the verdict is "same_as_rw", which is not tested`)
      else if (!same && nulls > 0) r.errors.push(`${at}: ${TESTED.join(', ')} must be numbers where the verdict is ${shown(verdict)}, which is tested`)
      else tested = same ? [null, null, null] : [r.num(raw[0], `${at}.statistic`), r.num(raw[1], `${at}.statistic_hln`), pValue(r, raw[2], `${at}.p_value`)]
    }
    const varRaw = r.field(row, 'var_diff', at)
    const [statistic, statisticHln, p] = tested
    return clean<DmRow>(r, start, {
      model_id: model,
      method,
      window,
      loss,
      n,
      max_forecast_gap: atLeast(r, r.field(row, 'max_forecast_gap', at), `${at}.max_forecast_gap`, 0, 'a distance'),
      mean_diff: r.num(r.field(row, 'mean_diff', at), `${at}.mean_diff`),
      var_diff: same ? atLeast(r, varRaw, `${at}.var_diff`, 0, 'a variance') : above(r, varRaw, `${at}.var_diff`, 0, 'a constant loss differential leaves DM undefined'),
      statistic,
      hln_factor: r.num(r.field(row, 'hln_factor', at), `${at}.hln_factor`),
      statistic_hln: statisticHln,
      df,
      p_value: p,
      verdict,
    })
  })
}

function parseCoverage(r: Reader, v: unknown, ns: WindowNs): CoverageRow[] | undefined {
  const what = 'one per forecast file, window, distribution (normal, then t) and level (0.8, then 0.95)'
  return rowSet(r, v, 'data.coverage', COVERAGE_KEYS, what, (row, at, [model0, method0, window0, dist0, level]) => {
    const start = r.errors.length
    const [model, method, window, distribution] = keyFields(r, row, at, [...FORECAST_KEY_FIELDS, ['distribution', DISTRIBUTIONS]], [model0, method0, window0, dist0] as const) as [
      ModelId | undefined,
      Method | undefined,
      WindowId | undefined,
      Distribution | undefined,
    ]
    const stated = r.num(r.field(row, 'level', at), `${at}.level`)
    const lv = pinNumber(r, stated, `${at}.level`, LEVELS[level], 'expects at this position the level')
    const n = windowN(r, r.field(row, 'n', at), `${at}.n`, window, ns)
    const inside = r.int(r.field(row, 'inside', at), `${at}.inside`)
    if (inside !== undefined && n !== undefined && inside > n) r.errors.push(`${at}.inside: is ${inside}, more than the window's ${n} days`)
    const lrRaw = r.field(row, 'lr', at)
    const pRaw = r.field(row, 'p_value', at)
    const verdict = r.choice(r.field(row, 'verdict', at), COVERAGE_VERDICTS, `${at}.verdict`) ?? undefined
    let lr: number | null | undefined
    let p: number | null | undefined
    // The method fixes these: a static path's days are not independent, so it is never tested.
    if (method !== undefined && lrRaw !== MISSING && pRaw !== MISSING) {
      if (KINDS[method] === 'multi_step') {
        if (lrRaw !== null || pRaw !== null) r.errors.push(`${at}: lr and p_value must be null for a multi_step forecast, which is not tested`)
        else lr = p = null
        if (verdict !== undefined && verdict !== 'not_tested') r.errors.push(`${at}.verdict: is ${shown(verdict)}, but a multi_step forecast is "not_tested"`)
      } else {
        if (lrRaw === null || pRaw === null) r.errors.push(`${at}: lr and p_value must be numbers for a one_step forecast, which is tested`)
        else {
          lr = r.num(lrRaw, `${at}.lr`)
          p = pValue(r, pRaw, `${at}.p_value`)
        }
        if (verdict === 'not_tested') r.errors.push(`${at}.verdict: is "not_tested", but a one_step forecast is tested`)
      }
    }
    return clean<CoverageRow>(r, start, {
      model_id: model,
      method,
      window,
      distribution,
      level: lv,
      n,
      inside,
      rate: r.num(r.field(row, 'rate', at), `${at}.rate`),
      lr,
      p_value: p,
      verdict,
    })
  })
}

/** Validates the `data` payload of the `evaluation` artifact (contract.md section 3.10). */
export function parseEvaluation(data: unknown): EvaluationResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  return capped(r.errors, 'data', () => readEvaluation(r, data))
}

/** parseEvaluation's body, stopped by `capped` at MAX_PROBLEMS problems. */
function readEvaluation(r: Reader, data: Record<string, unknown>): EvaluationResult {
  const alpha = pinNumber(r, r.num(r.field(data, 'alpha', 'data'), 'data.alpha'), 'data.alpha', ALPHA, 'reads the tests at alpha')
  const levels = pinList(r, r.field(data, 'interval_levels', 'data'), 'data.interval_levels', LEVELS, 'scores the intervals at levels')
  const refitEvery = pinNumber(r, r.int(r.field(data, 'refit_every', 'data'), 'data.refit_every', 1), 'data.refit_every', REFIT_EVERY, 're-estimates every')
  const headline = r.literal(r.field(data, 'headline_usd', 'data'), HEADLINE_USD, 'data.headline_usd')
  const dmSettings = parseDmSettings(r, r.field(data, 'dm_settings', 'data'))
  const { windows, ns } = parseEvaluationWindows(r, r.field(data, 'windows', 'data'))
  const models = parseModels(r, r.field(data, 'models', 'data'))
  const methods = parseMethods(r, r.field(data, 'methods', 'data'))
  const randomWalk = parseRandomWalk(r, r.field(data, 'random_walk', 'data'), ns)
  const metrics = parseMetrics(r, r.field(data, 'metrics', 'data'), ns)
  const dm = parseDm(r, r.field(data, 'dm', 'data'), ns)
  const coverage = parseCoverage(r, r.field(data, 'coverage', 'data'), ns)
  const evaluation = clean<Evaluation>(r, 0, {
    alpha,
    interval_levels: levels,
    refit_every: refitEvery,
    headline_usd: headline,
    dm_settings: dmSettings,
    windows,
    models,
    methods,
    random_walk: randomWalk,
    metrics,
    dm,
    coverage,
  })
  if (evaluation) return { ok: true, evaluation }
  return { ok: false, errors: r.errors.length > 0 ? r.errors : ['data: could not be read'] }
}

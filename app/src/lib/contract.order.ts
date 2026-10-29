/**
 * Payload parsers for the milestone-2 artifacts: `stationarity`, `acf_pacf` and `aic_grid`
 * (contract.md sections 3.4 to 3.6). The Python copy of every rule is in
 * src/arima_forecasting/payloads.py; the shared corpus (src/test/fixtures/payload_cases.json) runs
 * both, so a rule changed on one side only fails a test.
 *
 * Like the other parsers they collect every problem with a path, ignore unknown keys inside
 * `data`, and return a fresh object built from the keys they know. Some rules re-check what the
 * export decided (the 2 x 2 verdicts, the choice of d, each delta_aic, the selected cell). That is
 * validation, not computation: the app draws the exported values and never derives its own.
 *
 * In its own module so that only the two milestone-2 views bundle it.
 */
import { isRecord, typeName } from './contract'
import { MISSING, Reader } from './contract.reader'

export const TRANSFORM_IDS = ['log', 'diff1', 'diff2'] as const
export type TransformId = (typeof TRANSFORM_IDS)[number]
export const TRANSFORM_D: Record<TransformId, number> = { log: 0, diff1: 1, diff2: 2 }
export const VERDICTS = ['stationary', 'unit_root', 'conflict', 'inconclusive'] as const
export type Verdict = (typeof VERDICTS)[number]
export const TREND_CODES = ['c', 'n', 't'] as const
export type TrendCode = (typeof TREND_CODES)[number]
export const CELL_STATUSES = ['ok', 'not_converged', 'near_unit_root', 'failed'] as const
export type CellStatus = (typeof CELL_STATUSES)[number]
const CHECK_STATUSES = ['ok', 'unavailable'] as const
type CheckStatus = (typeof CHECK_STATUSES)[number]
const ADF_CRITICAL = ['1%', '5%', '10%'] as const
const KPSS_CRITICAL = ['10%', '5%', '2.5%', '1%'] as const

export interface AdfResult {
  statistic: number
  p_value: number
  used_lag: number
  maxlag: number
  nobs: number
  critical_values: Record<string, number>
  regression: string
  autolag: string
  reject_unit_root: boolean
}

export interface KpssResult {
  statistic: number
  p_value: number
  p_value_bound: 'smaller' | 'greater' | null
  nlags: number
  nlags_method: string
  critical_values: Record<string, number>
  regression: string
  reject_stationarity: boolean
}

export interface TestPair {
  adf: AdfResult
  kpss: KpssResult
  verdict: Verdict
}

export interface StationarityTransform extends TestPair {
  id: TransformId
  d: number
  n: number
  with_trend: TestPair
}

export interface NdiffsCheck {
  status: CheckStatus
  reason: string | null
  version: string | null
  kpss: number | null
  adf: number | null
  pp: number | null
  agrees: boolean | null
}

export interface Stationarity {
  sample: 'train'
  n_train: number
  alpha: number
  transforms: StationarityTransform[]
  decision: { d_selected: number; rule: string; tests_conflict: boolean; pmdarima_ndiffs: NdiffsCheck }
}

export interface CorrelogramRow {
  lag: number
  acf: number
  pacf: number
  acf_band: number
  pacf_band: number
  /** Python's verdict: |acf| > acf_band at this lag (never at lag 0). The app draws it; it does not recompute it. */
  acf_outside: boolean
  pacf_outside: boolean
}

export interface CorrelogramSeries {
  transform: TransformId
  d: number
  n: number
  /** Lags 1..nlags flagged outside their band, as exported. */
  acf_outside_count: number
  pacf_outside_count: number
  rows: CorrelogramRow[]
}

export interface AcfPacf {
  sample: 'train'
  nlags: number
  alpha: number
  z: number
  acf_settings: { fft: boolean; adjusted: boolean; bartlett_confint: boolean }
  pacf_method: string
  series: CorrelogramSeries[]
}

export interface AicCell {
  d: number
  p: number
  q: number
  trend: TrendCode
  status: CellStatus
  reason: string | null
  k_params: number
  aic: number | null
  bic: number | null
  llf: number | null
  delta_aic: number | null
  converged: boolean | null
  max_inv_root_ar: number | null
  max_inv_root_ma: number | null
  warnings: { category: string; message: string }[]
  error: string | null
  /** The start the kept run came from: 'default', 'random <k>' or 'nested (p, d, q) <trend>', optionally ', polished'; null when the cell failed. */
  start: string | null
  starts_tried: number
}

export interface CellRef {
  p: number
  q: number
  trend: TrendCode
  aic: number
}

export interface PmdarimaRun {
  label: string
  order: [number, number, number]
  with_intercept: boolean
  trend: TrendCode | null
  aic: number
  converged: boolean
  iterations: number
  visited: { order: [number, number, number]; with_intercept: boolean; aic: number }[]
  agreement: { d: boolean; order: boolean; trend: boolean; same_order_status: CellStatus | null; aic_gap_same_order: number | null }
}

export interface AicGrid {
  sample: 'train'
  n_train: number
  criterion: 'aic'
  grid: { p: number[]; q: number[]; specs: { d: number; trends: TrendCode[] }[] }
  fit_settings: { library: string; version: string; optimizer: string; maxiter: number; near_unit_root_threshold: number; random_starts: number; nesting_tolerance: number }
  cells: AicCell[]
  selection: {
    d_selected: number
    order: [number, number, number]
    trend: TrendCode
    aic: number
    bic: number
    k_params: number
    rule: string
    within_2_aic: (CellRef & { delta_aic: number })[]
    bic_choice: CellRef & { bic: number }
    best_per_d: { d: number; cell: CellRef | null }[]
    status_counts: ({ d: number } & Record<CellStatus, number>)[]
  }
  pmdarima_check: { status: CheckStatus; reason: string | null; version: string | null; runs: PmdarimaRun[] }
}

export type StationarityResult = { ok: true; stationarity: Stationarity } | { ok: false; errors: string[] }
export type AcfPacfResult = { ok: true; acfPacf: AcfPacf } | { ok: false; errors: string[] }
export type AicGridResult = { ok: true; aicGrid: AicGrid } | { ok: false; errors: string[] }

const show = (v: unknown) => JSON.stringify(v) ?? typeName(v)

/** The 2 x 2 table of concept note 05. */
export function tableVerdict(adfRejects: boolean, kpssRejects: boolean): Verdict {
  if (adfRejects) return kpssRejects ? 'conflict' : 'stationary'
  return kpssRejects ? 'unit_root' : 'inconclusive'
}

/** A non-empty string or null: the string, null, or undefined when invalid or missing. */
function strOrNull(r: Reader, v: unknown, at: string): string | null | undefined {
  if (v === null) return null
  return r.str(v, at)
}

function critical(r: Reader, v: unknown, keys: readonly string[], at: string): Record<string, number> | undefined {
  if (v === MISSING) return undefined
  const o = r.obj(v, at)
  if (!o) return undefined
  const out: Record<string, number> = {}
  for (const key of keys) {
    const x = r.num(r.field(o, key, at), `${at}.${key}`)
    if (x !== undefined) out[key] = x
  }
  return out
}

function parseAdf(r: Reader, v: unknown, at: string, regression: string, alpha: number | undefined): AdfResult | undefined {
  if (v === MISSING) return undefined
  const o = r.obj(v, at)
  if (!o) return undefined
  const before = r.errors.length
  const statistic = r.num(r.field(o, 'statistic', at), `${at}.statistic`)
  const p = r.num(r.field(o, 'p_value', at), `${at}.p_value`)
  if (p !== undefined && !(p >= 0 && p <= 1)) r.errors.push(`${at}.p_value: must be between 0 and 1, got ${p}`)
  const used = r.int(r.field(o, 'used_lag', at), `${at}.used_lag`)
  const maxlag = r.int(r.field(o, 'maxlag', at), `${at}.maxlag`)
  if (used !== undefined && maxlag !== undefined && used > maxlag) r.errors.push(`${at}.used_lag: ${used} is above maxlag ${maxlag}`)
  const nobs = r.int(r.field(o, 'nobs', at), `${at}.nobs`, 1)
  const crit = critical(r, r.field(o, 'critical_values', at), ADF_CRITICAL, `${at}.critical_values`)
  const reg = r.literal(r.field(o, 'regression', at), regression, `${at}.regression`)
  const autolag = r.literal(r.field(o, 'autolag', at), 'AIC', `${at}.autolag`)
  const reject = r.bool(r.field(o, 'reject_unit_root', at), `${at}.reject_unit_root`)
  if (reject !== undefined && p !== undefined && alpha !== undefined && reject !== p < alpha) {
    r.errors.push(`${at}.reject_unit_root: is ${reject}, but p_value ${p} < alpha ${alpha} is ${p < alpha}`)
  }
  if (r.errors.length > before || statistic === undefined || p === undefined || used === undefined || maxlag === undefined || nobs === undefined || !crit || !reg || !autolag || reject === undefined) return undefined
  return { statistic, p_value: p, used_lag: used, maxlag, nobs, critical_values: crit, regression: reg, autolag, reject_unit_root: reject }
}

function parseKpss(r: Reader, v: unknown, at: string, regression: string, alpha: number | undefined): KpssResult | undefined {
  if (v === MISSING) return undefined
  const o = r.obj(v, at)
  if (!o) return undefined
  const before = r.errors.length
  const statistic = r.num(r.field(o, 'statistic', at), `${at}.statistic`)
  if (statistic !== undefined && statistic < 0) r.errors.push(`${at}.statistic: must not be negative, got ${statistic}`)
  const p = r.num(r.field(o, 'p_value', at), `${at}.p_value`)
  // statsmodels interpolates inside a table that runs from 0.01 to 0.10, and clips at its edges.
  if (p !== undefined && !(p >= 0.01 && p <= 0.1)) r.errors.push(`${at}.p_value: must be between 0.01 and 0.10, got ${p}`)
  const bound = r.field(o, 'p_value_bound', at)
  let p_value_bound: KpssResult['p_value_bound'] | undefined
  if (bound !== MISSING) {
    if (bound !== null && bound !== 'smaller' && bound !== 'greater') r.errors.push(`${at}.p_value_bound: expected smaller, greater or null, got ${show(bound)}`)
    else if (p !== undefined) {
      const want = p === 0.01 ? 'smaller' : p === 0.1 ? 'greater' : null
      if (bound !== want) r.errors.push(`${at}.p_value_bound: is ${show(bound)}, but a p_value of ${p} means ${show(want)}`)
      else p_value_bound = want
    }
  }
  const nlags = r.int(r.field(o, 'nlags', at), `${at}.nlags`)
  const nlags_method = r.str(r.field(o, 'nlags_method', at), `${at}.nlags_method`)
  const crit = critical(r, r.field(o, 'critical_values', at), KPSS_CRITICAL, `${at}.critical_values`)
  const reg = r.literal(r.field(o, 'regression', at), regression, `${at}.regression`)
  const reject = r.bool(r.field(o, 'reject_stationarity', at), `${at}.reject_stationarity`)
  if (reject !== undefined && p !== undefined && alpha !== undefined && reject !== p < alpha) {
    r.errors.push(`${at}.reject_stationarity: is ${reject}, but p_value ${p} < alpha ${alpha} is ${p < alpha}`)
  }
  if (r.errors.length > before || statistic === undefined || p === undefined || p_value_bound === undefined || nlags === undefined || !nlags_method || !crit || !reg || reject === undefined) return undefined
  return { statistic, p_value: p, p_value_bound, nlags, nlags_method, critical_values: crit, regression: reg, reject_stationarity: reject }
}

function parseVerdict(r: Reader, v: unknown, adf: AdfResult | undefined, kpss: KpssResult | undefined, at: string): Verdict | undefined {
  const verdict = r.choice(v, VERDICTS, at)
  if (!verdict) return undefined
  if (adf && kpss) {
    const want = tableVerdict(adf.reject_unit_root, kpss.reject_stationarity)
    if (verdict !== want) {
      r.errors.push(`${at}: is "${verdict}", but ADF reject ${adf.reject_unit_root} and KPSS reject ${kpss.reject_stationarity} make it "${want}"`)
      return undefined
    }
  }
  return verdict
}

function parseNdiffs(r: Reader, v: unknown, dSelected: number | undefined): NdiffsCheck | undefined {
  const at = 'data.decision.pmdarima_ndiffs'
  if (v === MISSING) return undefined
  const o = r.obj(v, at)
  if (!o) return undefined
  const before = r.errors.length
  const status = r.choice(r.field(o, 'status', at), CHECK_STATUSES, `${at}.status`)
  const reason = r.field(o, 'reason', at)
  const version = r.field(o, 'version', at)
  r.num(r.field(o, 'alpha', at), `${at}.alpha`)
  const maxD = r.int(r.field(o, 'max_d', at), `${at}.max_d`)
  const tests = ['kpss', 'adf', 'pp'] as const
  const found = tests.map((t) => [t, r.field(o, t, at)] as const)
  const agrees = r.field(o, 'agrees', at)
  if (status === 'ok') {
    if (reason !== MISSING && reason !== null) r.errors.push(`${at}.reason: must be null when status is ok, got ${show(reason)}`)
    if (version !== MISSING) r.str(version, `${at}.version`)
    const values = found.map(([t, value]) => {
      const x = r.int(value, `${at}.${t}`)
      if (x !== undefined && maxD !== undefined && x > maxD) r.errors.push(`${at}.${t}: ${x} is above max_d ${maxD}`)
      return x
    })
    const ok = r.bool(agrees, `${at}.agrees`)
    if (ok !== undefined && dSelected !== undefined && values.every((x) => x !== undefined) && ok !== values.every((x) => x === dSelected)) {
      r.errors.push(`${at}.agrees: is ${ok}, but kpss, adf and pp are ${show(values)} and d_selected is ${dSelected}`)
    }
  } else if (status === 'unavailable') {
    if (reason !== MISSING) r.str(reason, `${at}.reason`)
    if (version !== MISSING) strOrNull(r, version, `${at}.version`)
    for (const [t, value] of [...found, ['agrees', agrees] as const]) {
      if (value !== MISSING && value !== null) r.errors.push(`${at}.${t}: must be null when status is unavailable, got ${show(value)}`)
    }
  }
  if (r.errors.length > before || !status) return undefined
  const num = (x: unknown) => (typeof x === 'number' ? x : null)
  return {
    status,
    reason: typeof reason === 'string' ? reason : null,
    version: typeof version === 'string' ? version : null,
    kpss: num(o.kpss),
    adf: num(o.adf),
    pp: num(o.pp),
    agrees: typeof agrees === 'boolean' ? agrees : null,
  }
}

/** Validates the `data` payload of the `stationarity` artifact (contract.md section 3.4). */
export function parseStationarity(data: unknown): StationarityResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  const sample = r.literal(r.field(data, 'sample', 'data'), 'train', 'data.sample')
  const nTrain = r.int(r.field(data, 'n_train', 'data'), 'data.n_train', 3)
  let alpha = r.num(r.field(data, 'alpha', 'data'), 'data.alpha')
  if (alpha !== undefined && !(alpha > 0 && alpha < 1)) {
    r.errors.push(`data.alpha: must be between 0 and 1, got ${alpha}`)
    alpha = undefined
  }
  const list = r.arr(r.field(data, 'transforms', 'data'), 'data.transforms')
  const transforms: (StationarityTransform | undefined)[] = []
  const tests: ({ d: number; adf: boolean; kpss: boolean } | undefined)[] = []
  if (list) {
    if (list.length === 0) r.errors.push('data.transforms: must not be empty')
    let previous: number | undefined
    list.forEach((item, i) => {
      const at = `data.transforms[${i}]`
      const t = r.obj(item, at)
      if (!t) {
        tests.push(undefined)
        transforms.push(undefined)
        return
      }
      const id = r.choice(r.field(t, 'id', at), TRANSFORM_IDS, `${at}.id`)
      const d = r.int(r.field(t, 'd', at), `${at}.d`)
      if (id && d !== undefined && TRANSFORM_D[id] !== d) r.errors.push(`${at}.d: is ${d}, but "${id}" has d = ${TRANSFORM_D[id]}`)
      if (d !== undefined) {
        if (previous !== undefined && d <= previous) r.errors.push(`${at}.d: ${d} does not come after ${previous}; transforms are sorted by d`)
        previous = d
      }
      const n = r.int(r.field(t, 'n', at), `${at}.n`, 1)
      if (n !== undefined && d !== undefined && nTrain !== undefined && n !== nTrain - d) r.errors.push(`${at}.n: is ${n}, but n_train - d is ${nTrain - d}`)
      const adf = parseAdf(r, r.field(t, 'adf', at), `${at}.adf`, 'c', alpha)
      const kpss = parseKpss(r, r.field(t, 'kpss', at), `${at}.kpss`, 'c', alpha)
      const verdict = parseVerdict(r, r.field(t, 'verdict', at), adf, kpss, `${at}.verdict`)
      let withTrend: TestPair | undefined
      const wtRaw = r.field(t, 'with_trend', at)
      if (wtRaw !== MISSING) {
        const wt = r.obj(wtRaw, `${at}.with_trend`)
        if (wt) {
          const tadf = parseAdf(r, r.field(wt, 'adf', `${at}.with_trend`), `${at}.with_trend.adf`, 'ct', alpha)
          const tkpss = parseKpss(r, r.field(wt, 'kpss', `${at}.with_trend`), `${at}.with_trend.kpss`, 'ct', alpha)
          const tverdict = parseVerdict(r, r.field(wt, 'verdict', `${at}.with_trend`), tadf, tkpss, `${at}.with_trend.verdict`)
          if (tadf && tkpss && tverdict) withTrend = { adf: tadf, kpss: tkpss, verdict: tverdict }
        }
      }
      tests.push(d === undefined || !adf || !kpss ? undefined : { d, adf: adf.reject_unit_root, kpss: kpss.reject_stationarity })
      transforms.push(id && d !== undefined && n !== undefined && adf && kpss && verdict && withTrend ? { id, d, n, adf, kpss, verdict, with_trend: withTrend } : undefined)
    })
  }

  let decision: Stationarity['decision'] | undefined
  const dcRaw = r.field(data, 'decision', 'data')
  if (dcRaw !== MISSING) {
    const dc = r.obj(dcRaw, 'data.decision')
    if (dc) {
      const at = 'data.decision'
      const dSelected = r.int(r.field(dc, 'd_selected', at), `${at}.d_selected`)
      const rule = r.str(r.field(dc, 'rule', at), `${at}.rule`)
      const conflict = r.bool(r.field(dc, 'tests_conflict', at), `${at}.tests_conflict`)
      const complete = list !== undefined && list.length > 0 && tests.every((t) => t !== undefined)
      if (complete && dSelected !== undefined && conflict !== undefined) {
        // ADR-0002 section 2: the smallest d where ADF rejects and KPSS does not; else the smallest
        // d where KPSS does not reject; else the largest d. Re-applied here.
        const ordered = (tests as { d: number; adf: boolean; kpss: boolean }[]).slice().sort((a, b) => a.d - b.d)
        const passing = ordered.filter((t) => t.adf && !t.kpss)
        const fallback = ordered.filter((t) => !t.kpss)
        const want: [number, boolean] = passing.length > 0 ? [passing[0].d, false] : fallback.length > 0 ? [fallback[0].d, true] : [ordered[ordered.length - 1].d, true]
        if (dSelected !== want[0] || conflict !== want[1]) r.errors.push(`${at}: says d = ${dSelected} with tests_conflict ${conflict}, but the rule gives d = ${want[0]} with ${want[1]}`)
      }
      const ndiffs = parseNdiffs(r, r.field(dc, 'pmdarima_ndiffs', at), dSelected)
      if (dSelected !== undefined && complete && !tests.some((t) => t?.d === dSelected)) r.errors.push(`${at}.d_selected: ${dSelected} is not the d of any transform`)
      if (dSelected !== undefined && rule && conflict !== undefined && ndiffs) decision = { d_selected: dSelected, rule, tests_conflict: conflict, pmdarima_ndiffs: ndiffs }
    }
  }
  if (r.errors.length > 0 || !sample || nTrain === undefined || alpha === undefined || !list || !decision || transforms.some((t) => !t)) return { ok: false, errors: r.errors }
  return { ok: true, stationarity: { sample, n_train: nTrain, alpha, transforms: transforms as StationarityTransform[], decision } }
}

/** Validates the `data` payload of the `acf_pacf` artifact (contract.md section 3.5). */
export function parseAcfPacf(data: unknown): AcfPacfResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  const sample = r.literal(r.field(data, 'sample', 'data'), 'train', 'data.sample')
  const nlags = r.int(r.field(data, 'nlags', 'data'), 'data.nlags', 1)
  const alpha = r.num(r.field(data, 'alpha', 'data'), 'data.alpha')
  if (alpha !== undefined && !(alpha > 0 && alpha < 1)) r.errors.push(`data.alpha: must be between 0 and 1, got ${alpha}`)
  const z = r.num(r.field(data, 'z', 'data'), 'data.z')
  if (z !== undefined && z <= 0) r.errors.push(`data.z: must be positive, got ${z}`)
  else if (z !== undefined && alpha !== undefined && Z_FOR_ALPHA.get(alpha) !== z) {
    const known = Z_FOR_ALPHA.get(alpha)
    r.errors.push(known !== undefined ? `data.z: is ${z}, but the two-sided z for alpha ${alpha} is ${known}` : `data.z: no z is listed for alpha ${alpha}; this reader knows ${[...Z_FOR_ALPHA.keys()].join(', ')}`)
  }
  let settings: AcfPacf['acf_settings'] | undefined
  const stRaw = r.field(data, 'acf_settings', 'data')
  if (stRaw !== MISSING) {
    const st = r.obj(stRaw, 'data.acf_settings')
    if (st) {
      const [fft, adjusted, bartlett] = (['fft', 'adjusted', 'bartlett_confint'] as const).map((k) => r.bool(r.field(st, k, 'data.acf_settings'), `data.acf_settings.${k}`))
      if (fft !== undefined && adjusted !== undefined && bartlett !== undefined) settings = { fft, adjusted, bartlett_confint: bartlett }
    }
  }
  const pacfMethod = r.str(r.field(data, 'pacf_method', 'data'), 'data.pacf_method')
  const list = r.arr(r.field(data, 'series', 'data'), 'data.series')
  const series: CorrelogramSeries[] = []
  if (list) {
    if (list.length === 0) r.errors.push('data.series: must not be empty')
    let previous: number | undefined
    list.forEach((item, i) => {
      const at = `data.series[${i}]`
      const s = r.obj(item, at)
      if (!s) return
      const transform = r.choice(r.field(s, 'transform', at), TRANSFORM_IDS, `${at}.transform`)
      const d = r.int(r.field(s, 'd', at), `${at}.d`)
      if (transform && d !== undefined && TRANSFORM_D[transform] !== d) r.errors.push(`${at}.d: is ${d}, but "${transform}" has d = ${TRANSFORM_D[transform]}`)
      if (d !== undefined) {
        if (previous !== undefined && d <= previous) r.errors.push(`${at}.d: ${d} does not come after ${previous}; series are sorted by d`)
        previous = d
      }
      const n = r.int(r.field(s, 'n', at), `${at}.n`, 2)
      const counts = (['acf', 'pacf'] as const).map((name) => r.int(r.field(s, `${name}_outside_count`, at), `${at}.${name}_outside_count`))
      const rowsRaw = r.arr(r.field(s, 'rows', at), `${at}.rows`)
      if (!rowsRaw) return
      const flagged: Record<'acf' | 'pacf', (boolean | undefined)[]> = { acf: [], pacf: [] }
      if (nlags !== undefined && rowsRaw.length !== nlags + 1) r.errors.push(`${at}.rows: has ${rowsRaw.length} rows, but lags 0 to ${nlags} make ${nlags + 1}`)
      const rows: CorrelogramRow[] = []
      rowsRaw.forEach((itemRow, k) => {
        const rat = `${at}.rows[${k}]`
        const row = r.obj(itemRow, rat)
        if (!row) return
        const lag = r.int(r.field(row, 'lag', rat), `${rat}.lag`)
        if (lag !== undefined && lag !== k) r.errors.push(`${rat}.lag: is ${lag}, expected ${k}`)
        const values = (['acf', 'pacf'] as const).map((name) => {
          const v = r.num(r.field(row, name, rat), `${rat}.${name}`)
          if (v !== undefined && !(v >= -1 && v <= 1)) r.errors.push(`${rat}.${name}: must be between -1 and 1, got ${v}`)
          if (v !== undefined && k === 0 && v !== 1) r.errors.push(`${rat}.${name}: is ${v} at lag 0, where it is 1 by definition`)
          return v
        })
        const bands = (['acf_band', 'pacf_band'] as const).map((name) => {
          const b = r.num(r.field(row, name, rat), `${rat}.${name}`)
          if (b !== undefined && (k === 0 ? b !== 0 : b <= 0)) r.errors.push(`${rat}.${name}: is ${b}; a band is 0 at lag 0 and positive at every other lag`)
          return b
        })
        const [acf, pacf] = values
        const [acf_band, pacf_band] = bands
        const flags = (['acf', 'pacf'] as const).map((name, j) => {
          const flag = r.bool(r.field(row, `${name}_outside`, rat), `${rat}.${name}_outside`)
          flagged[name].push(flag)
          const value = values[j]
          const band = bands[j]
          // Checked only when the value and the band passed their own checks above.
          if (flag !== undefined && value !== undefined && band !== undefined && value >= -1 && value <= 1 && (k === 0 ? band === 0 : band > 0)) {
            const want = k >= 1 && Math.abs(value) > band
            if (flag !== want) r.errors.push(`${rat}.${name}_outside: is ${flag}, but |${name}| ${Math.abs(value)} ${Math.abs(value) > band ? '>' : '<='} band ${band} at lag ${k}`)
          }
          return flag
        })
        const [acf_outside, pacf_outside] = flags
        if (lag !== undefined && acf !== undefined && pacf !== undefined && acf_band !== undefined && pacf_band !== undefined && acf_outside !== undefined && pacf_outside !== undefined) {
          rows.push({ lag, acf, pacf, acf_band, pacf_band, acf_outside, pacf_outside })
        }
      })
      ;(['acf', 'pacf'] as const).forEach((name, j) => {
        const count = counts[j]
        const flags = flagged[name]
        if (count !== undefined && flags.every((f) => f !== undefined) && count !== flags.filter((f) => f).length) {
          r.errors.push(`${at}.${name}_outside_count: is ${count}, but ${flags.filter((f) => f).length} rows are flagged`)
        }
      })
      const [acfCount, pacfCount] = counts
      if (transform && d !== undefined && n !== undefined && acfCount !== undefined && pacfCount !== undefined) {
        series.push({ transform, d, n, acf_outside_count: acfCount, pacf_outside_count: pacfCount, rows })
      }
    })
  }
  if (r.errors.length > 0 || !sample || nlags === undefined || alpha === undefined || z === undefined || !settings || !pacfMethod || !list) return { ok: false, errors: r.errors }
  return { ok: true, acfPacf: { sample, nlags, alpha, z, acf_settings: settings, pacf_method: pacfMethod, series } }
}

/**
 * The two-sided normal quantile z = Phi^-1(1 - alpha / 2) for each alpha a payload may use: the same
 * exact doubles as payloads.Z_FOR_ALPHA (scipy's norm.ppf(0.975)). A new alpha needs a row in both.
 */
export const Z_FOR_ALPHA: ReadonlyMap<number, number> = new Map([[0.05, 1.959963984540054]])

/** A cell's place in the ranking: lowest criterion, then fewer parameters, smaller p + q, smaller p, the trend code. */
function before(a: AicCell, b: AicCell, key: 'aic' | 'bic'): boolean {
  const x: (number | string)[] = [a[key] as number, a.k_params, a.p + a.q, a.p, a.trend]
  const y: (number | string)[] = [b[key] as number, b.k_params, b.p + b.q, b.p, b.trend]
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] < y[i]
  return false
}

function lowest(cells: AicCell[], key: 'aic' | 'bic'): AicCell | undefined {
  let best: AicCell | undefined
  for (const c of cells) if (best === undefined || before(c, best, key)) best = c
  return best
}

function triple(r: Reader, v: unknown, at: string): [number, number, number] | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  if (list.length !== 3) {
    r.errors.push(`${at}: expected [p, d, q], got ${show(list)}`)
    return undefined
  }
  const out = list.map((x, i) => r.int(x, `${at}[${i}]`))
  return out.every((x) => x !== undefined) ? (out as [number, number, number]) : undefined
}

function axis(r: Reader, v: unknown, at: string): number[] | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  const out = list.map((x, i) => r.int(x, `${at}[${i}]`))
  if (out.length === 0) r.errors.push(`${at}: must not be empty`)
  if (out.some((x) => x === undefined)) return undefined
  const values = out as number[]
  if (values.some((x, i) => i > 0 && x <= values[i - 1])) {
    r.errors.push(`${at}: must be strictly ascending, got ${show(values)}`)
    return undefined
  }
  return values
}

function parseCell(r: Reader, item: unknown, at: string, nTrain: number | undefined, threshold: number | undefined): AicCell | undefined {
  const cell = r.obj(item, at)
  if (!cell) return undefined
  const start = r.errors.length
  const d = r.int(r.field(cell, 'd', at), `${at}.d`)
  const p = r.int(r.field(cell, 'p', at), `${at}.p`)
  const q = r.int(r.field(cell, 'q', at), `${at}.q`)
  const trend = r.choice(r.field(cell, 'trend', at), TREND_CODES, `${at}.trend`)
  const status = r.choice(r.field(cell, 'status', at), CELL_STATUSES, `${at}.status`)
  const k = r.int(r.field(cell, 'k_params', at), `${at}.k_params`, 1)
  if (p !== undefined && q !== undefined && trend && k !== undefined && k !== p + q + (trend !== 'n' ? 1 : 0) + 1) {
    r.errors.push(`${at}.k_params: is ${k}, but p + q + trend terms + sigma2 is ${p + q + (trend !== 'n' ? 1 : 0) + 1}`)
  }
  const reason = r.field(cell, 'reason', at)
  if (reason !== MISSING && status) {
    if (status === 'ok' && reason !== null) r.errors.push(`${at}.reason: must be null for an ok cell, got ${show(reason)}`)
    else if (status !== 'ok') r.str(reason, `${at}.reason`)
  }
  const warnsRaw = r.arr(r.field(cell, 'warnings', at), `${at}.warnings`)
  const warnings: AicCell['warnings'] = []
  ;(warnsRaw ?? []).forEach((w, i) => {
    const wo = r.obj(w, `${at}.warnings[${i}]`)
    if (!wo) return
    const category = r.str(r.field(wo, 'category', `${at}.warnings[${i}]`), `${at}.warnings[${i}].category`)
    const message = r.field(wo, 'message', `${at}.warnings[${i}]`)
    if (message !== MISSING && typeof message !== 'string') r.errors.push(`${at}.warnings[${i}].message: expected a string, got ${show(message)}`)
    if (category && typeof message === 'string') warnings.push({ category, message })
  })
  const FIELDS = ['aic', 'aicc', 'bic', 'llf', 'nobs_effective', 'converged', 'iterations', 'warnflag', 'max_inv_root_ar', 'max_inv_root_ma', 'delta_aic', 'start', 'params'] as const
  const raw = Object.fromEntries([...FIELDS, 'error'].map((name) => [name, r.field(cell, name, at)])) as Record<string, unknown>
  const startsTried = r.int(r.field(cell, 'starts_tried', at), `${at}.starts_tried`, 1)
  let aic: number | null | undefined = null
  let bic: number | null | undefined = null
  let llf: number | null | undefined = null
  let startLabel: string | null | undefined = null
  let delta: number | null | undefined = null
  let converged: boolean | null | undefined = null
  const roots: Record<'max_inv_root_ar' | 'max_inv_root_ma', number | null | undefined> = { max_inv_root_ar: null, max_inv_root_ma: null }
  if (status === 'failed') {
    for (const name of FIELDS) if (raw[name] !== MISSING && raw[name] !== null) r.errors.push(`${at}.${name}: must be null for a failed cell, got ${show(raw[name])}`)
    if (raw.error !== MISSING) r.str(raw.error, `${at}.error`)
  } else if (status) {
    if (raw.error !== MISSING && raw.error !== null) r.errors.push(`${at}.error: must be null unless the cell failed, got ${show(raw.error)}`)
    aic = r.num(raw.aic, `${at}.aic`)
    r.num(raw.aicc, `${at}.aicc`)
    bic = r.num(raw.bic, `${at}.bic`)
    llf = r.num(raw.llf, `${at}.llf`)
    startLabel = r.str(raw.start, `${at}.start`)
    if (startLabel !== undefined && !START.test(startLabel)) {
      r.errors.push(`${at}.start: must be ${START_GRAMMAR}, got ${show(startLabel)}`)
    }
    const params = raw.params === MISSING ? undefined : r.obj(raw.params, `${at}.params`)
    if (params) {
      if (k !== undefined && Object.keys(params).length !== k) r.errors.push(`${at}.params: has ${Object.keys(params).length} entries, but k_params is ${k}`)
      for (const [name, value] of Object.entries(params)) r.num(value, `${at}.params.${name}`)
    }
    const nobs = r.int(raw.nobs_effective, `${at}.nobs_effective`, 1)
    if (nobs !== undefined && nTrain !== undefined && d !== undefined && nobs !== nTrain - d) r.errors.push(`${at}.nobs_effective: is ${nobs}, but n_train - d is ${nTrain - d}`)
    converged = r.bool(raw.converged, `${at}.converged`)
    r.int(raw.iterations, `${at}.iterations`)
    r.int(raw.warnflag, `${at}.warnflag`)
    for (const [name, order] of [['max_inv_root_ar', p], ['max_inv_root_ma', q]] as const) {
      const value = raw[name]
      if (order === 0) {
        if (value !== MISSING && value !== null) r.errors.push(`${at}.${name}: must be null when the order is 0, got ${show(value)}`)
        roots[name] = null
      } else {
        const x = r.num(value, `${at}.${name}`)
        if (x !== undefined && x < 0) r.errors.push(`${at}.${name}: must not be negative, got ${x}`)
        roots[name] = x
      }
    }
    if (converged !== undefined && converged !== null && threshold !== undefined && p !== undefined && q !== undefined && r.errors.length === start) {
      const near = Object.values(roots).some((x) => x !== null && x !== undefined && x > threshold)
      const want = !converged ? 'not_converged' : near ? 'near_unit_root' : 'ok'
      if (status !== want) r.errors.push(`${at}.status: is "${status}", but converged ${converged} and the root moduli make it "${want}"`)
    }
    delta = raw.delta_aic === MISSING ? null : r.numOrNull(raw.delta_aic, `${at}.delta_aic`)
  }
  if (r.errors.length > start || d === undefined || p === undefined || q === undefined || !trend || !status || k === undefined || startsTried === undefined) return undefined
  return {
    d,
    p,
    q,
    trend,
    status,
    reason: typeof reason === 'string' ? reason : null,
    k_params: k,
    aic: aic ?? null,
    bic: bic ?? null,
    llf: llf ?? null,
    delta_aic: delta ?? null,
    converged: converged ?? null,
    max_inv_root_ar: roots.max_inv_root_ar ?? null,
    max_inv_root_ma: roots.max_inv_root_ma ?? null,
    warnings,
    error: typeof raw.error === 'string' ? raw.error : null,
    start: startLabel ?? null,
    starts_tried: startsTried,
  }
}

/** The start a cell's kept run came from (selection.py): the default, the k-th seeded random start, or a nested model one step smaller; ", polished" when restarted from its own estimates. */
const START = /^(?:(?:default|random ([1-9][0-9]*)|nested \(([0-9]+), ([0-9]+), ([0-9]+)\) ([nct])(, perturbed [+-])?)(, polished)?|polished from \(([0-9]+), ([0-9]+), ([0-9]+)\) ([nct]))$/
const START_GRAMMAR = "'default', 'random <k>', 'nested (p, d, q) <trend>' (optionally ', perturbed +' or '-'), each optionally followed by ', polished', or 'polished from (p, d, q) <trend>'"
/** The largest log-likelihood a cell may lose against a model it nests: payloads.NESTING_TOLERANCE, pinned, never read from the file. */
export const NESTING_TOLERANCE = 2e-3

/** `small` is a special case of `big`: same d, no more AR or MA lags, the same trend or none. */
function nests(small: AicCell, big: AicCell): boolean {
  const same = small.d === big.d && small.p === big.p && small.q === big.q && small.trend === big.trend
  return !same && small.d === big.d && small.p <= big.p && small.q <= big.q && (small.trend === big.trend || small.trend === 'n')
}

/** A random start must be one the settings drew; a nested start must be a model of the grid one step smaller than the cell. */
function checkStarts(r: Reader, cells: AicCell[], specs: { d: number; trends: TrendCode[] }[], ps: number[], qs: number[], randomStarts: number | undefined) {
  cells.forEach((x, i) => {
    if (x.start === null) return
    const m = START.exec(x.start)
    if (!m) return
    const at = `data.cells[${i}].start`
    if (m[1] !== undefined) {
      if (randomStarts !== undefined && Number(m[1]) > randomStarts) r.errors.push(`${at}: is ${show(m[0])}, but fit_settings.random_starts is ${randomStarts}`)
      if (x.p === 0 || x.q === 0) r.errors.push(`${at}: is ${show(m[0])}, but random starts are drawn only when p and q are both at least 1`)
    } else if (m[8] !== undefined) {
      const [sp, sd, sq, st] = [Number(m[8]), Number(m[9]), Number(m[10]), m[11]]
      const trendsOfD = specs.find((s) => s.d === x.d)?.trends ?? []
      if (sd !== x.d || !ps.includes(sp) || !qs.includes(sq) || !(trendsOfD as string[]).includes(st)) r.errors.push(`${at}: is ${show(m[0])}, which is not a cell of the grid with the same d`)
    } else if (m[2] !== undefined) {
      const [sp, sd, sq, st] = [Number(m[2]), Number(m[3]), Number(m[4]), m[5]]
      if (m[6] !== undefined && sp === x.p && sq === x.q) r.errors.push(`${at}: is ${show(m[0])}, but the step that drops the trend adds no AR or MA coefficient to perturb`)
      const steps: [number, number, string][] = []
      const pi = ps.indexOf(x.p)
      const qi = qs.indexOf(x.q)
      if (pi > 0) steps.push([ps[pi - 1], x.q, x.trend])
      if (qi > 0) steps.push([x.p, qs[qi - 1], x.trend])
      if (x.trend !== 'n' && (specs.find((s) => s.d === x.d)?.trends ?? []).includes('n')) steps.push([x.p, x.q, 'n'])
      if (sd !== x.d || !steps.some(([a, b, c]) => a === sp && b === sq && c === st)) {
        r.errors.push(`${at}: is ${show(m[0])}, which is not a model of the grid one step smaller than (${x.p}, ${x.d}, ${x.q}) ${x.trend}`)
      }
    }
  })
}

/** No fitted cell may score a lower log-likelihood than a model it nests by more than the tolerance: that is a local optimum. */
function checkNesting(r: Reader, cells: AicCell[], tolerance: number) {
  cells.forEach((big, i) => {
    if (big.llf === null) return
    for (const small of cells) {
      if (small.llf !== null && nests(small, big) && big.llf < small.llf - tolerance) {
        r.errors.push(`data.cells[${i}].llf: is ${big.llf}, below the ${small.llf} of (${small.p}, ${small.d}, ${small.q}) ${small.trend}, a model it nests, by more than ${tolerance}`)
      }
    }
  })
}

type FieldKind = 'int' | 'trend' | 'number'
/** A typed view of a small object: each known field type-checked, unknown keys ignored. */
function fields(r: Reader, v: unknown, at: string, spec: [string, FieldKind][]): Record<string, number | string> | undefined {
  if (v === MISSING) return undefined
  const o = r.obj(v, at)
  if (!o) return undefined
  const start = r.errors.length
  const out: Record<string, number | string> = {}
  for (const [name, kind] of spec) {
    const value = r.field(o, name, at)
    const x = kind === 'int' ? r.int(value, `${at}.${name}`) : kind === 'trend' ? r.choice(value, TREND_CODES, `${at}.${name}`) : r.num(value, `${at}.${name}`)
    if (x !== undefined && x !== null) out[name] = x
  }
  return r.errors.length === start ? out : undefined
}

const NEAR_TIE_FIELDS: [string, FieldKind][] = [['p', 'int'], ['q', 'int'], ['trend', 'trend'], ['aic', 'number'], ['delta_aic', 'number']]
const BIC_FIELDS: [string, FieldKind][] = [['p', 'int'], ['q', 'int'], ['trend', 'trend'], ['aic', 'number'], ['bic', 'number']]
const BEST_FIELDS: [string, FieldKind][] = [['p', 'int'], ['q', 'int'], ['trend', 'trend'], ['aic', 'number']]
const COUNT_FIELDS: [string, FieldKind][] = [['d', 'int'], ...CELL_STATUSES.map((s): [string, FieldKind] => [s, 'int'])]

function listOf(r: Reader, v: unknown, at: string, spec: [string, FieldKind][]): Record<string, number | string>[] | undefined {
  const list = r.arr(v, at)
  if (!list) return undefined
  const parsed = list.map((item, i) => fields(r, item, `${at}[${i}]`, spec))
  return parsed.every((x) => x !== undefined) ? (parsed as Record<string, number | string>[]) : undefined
}

function sameValues(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i])
}

function parseRun(r: Reader, item: unknown, at: string, cells: AicCell[] | undefined, chosen: { d: number; order: [number, number, number]; trend: TrendCode } | undefined): PmdarimaRun | undefined {
  const run = r.obj(item, at)
  if (!run) return undefined
  const start = r.errors.length
  const label = r.str(r.field(run, 'label', at), `${at}.label`)
  const settings = r.field(run, 'settings', at)
  if (settings !== MISSING) r.obj(settings, `${at}.settings`)
  const order = triple(r, r.field(run, 'order', at), `${at}.order`)
  const intercept = r.bool(r.field(run, 'with_intercept', at), `${at}.with_intercept`)
  const beforeTrend = r.errors.length
  const trend = r.choice(r.field(run, 'trend', at), TREND_CODES, `${at}.trend`, true)
  const trendOk = Object.hasOwn(run, 'trend') && r.errors.length === beforeTrend
  if (order && intercept !== undefined && trendOk) {
    const want = !intercept ? 'n' : order[1] === 0 ? 'c' : order[1] === 1 ? 't' : null
    if (trend !== want) r.errors.push(`${at}.trend: is ${show(trend)}, but d = ${order[1]} with_intercept ${intercept} is ${show(want)}`)
  }
  const aic = r.num(r.field(run, 'aic', at), `${at}.aic`)
  const converged = r.bool(r.field(run, 'converged', at), `${at}.converged`)
  const iterations = r.int(r.field(run, 'iterations', at), `${at}.iterations`)
  const visitedRaw = r.arr(r.field(run, 'visited', at), `${at}.visited`)
  const visited: PmdarimaRun['visited'] = []
  if (visitedRaw) {
    if (visitedRaw.length === 0) r.errors.push(`${at}.visited: must not be empty: the chosen model is its first entry`)
    visitedRaw.forEach((v, j) => {
      const vat = `${at}.visited[${j}]`
      const vo = r.obj(v, vat)
      if (!vo) return
      const vorder = triple(r, r.field(vo, 'order', vat), `${vat}.order`)
      const vint = r.bool(r.field(vo, 'with_intercept', vat), `${vat}.with_intercept`)
      const vaic = r.num(r.field(vo, 'aic', vat), `${vat}.aic`)
      if (j === 0 && vorder && vint !== undefined && vaic !== undefined && order && intercept !== undefined && aic !== undefined && !(sameValues(vorder, order) && vint === intercept && vaic === aic)) {
        r.errors.push(`${vat}: must be the chosen model: the same order, with_intercept and aic as the run`)
      }
      if (vorder && vint !== undefined && vaic !== undefined) visited.push({ order: vorder, with_intercept: vint, aic: vaic })
    })
  }
  const warns = r.arr(r.field(run, 'warnings', at), `${at}.warnings`)
  ;(warns ?? []).forEach((w, j) => {
    const wo = r.obj(w, `${at}.warnings[${j}]`)
    if (wo) r.str(r.field(wo, 'category', `${at}.warnings[${j}]`), `${at}.warnings[${j}].category`)
  })
  const agRaw = r.field(run, 'agreement', at)
  let agreement: PmdarimaRun['agreement'] | undefined
  if (agRaw !== MISSING) {
    const ag = r.obj(agRaw, `${at}.agreement`)
    if (ag) {
      const aat = `${at}.agreement`
      const agStart = r.errors.length
      const flags = (['d', 'order', 'trend'] as const).map((name) => r.bool(r.field(ag, name, aat), `${aat}.${name}`))
      const status = r.choice(r.field(ag, 'same_order_status', aat), CELL_STATUSES, `${aat}.same_order_status`, true)
      const gapRaw = r.field(ag, 'aic_gap_same_order', aat)
      const gap = gapRaw === MISSING ? undefined : r.numOrNull(gapRaw, `${aat}.aic_gap_same_order`)
      if (r.errors.length === agStart && order && aic !== undefined && trendOk && status !== undefined && gap !== undefined) {
        if (chosen) {
          const want = [order[1] === chosen.d, sameValues(order, chosen.order), trend === chosen.trend]
          if (!sameValues(flags, want)) r.errors.push(`${aat}: d, order and trend say ${show(flags)}, but comparing with the selection gives ${show(want)}`)
        }
        if (cells) {
          const same = cells.find((c) => c.d === order[1] && c.p === order[0] && c.q === order[2] && c.trend === trend)
          const wantStatus = same ? same.status : null
          const wantGap = !same || same.aic === null ? null : aic - same.aic
          if (status !== wantStatus || gap !== wantGap) r.errors.push(`${aat}: same_order_status ${show(status)} and aic_gap_same_order ${show(gap)} must be ${show(wantStatus)} and ${show(wantGap)}`)
        }
        const [fd, fo, ft] = flags as boolean[]
        agreement = { d: fd, order: fo, trend: ft, same_order_status: status, aic_gap_same_order: gap }
      }
    }
  }
  if (r.errors.length > start || !label || !order || intercept === undefined || !trendOk || aic === undefined || converged === undefined || iterations === undefined || !agreement) return undefined
  return { label, order, with_intercept: intercept, trend: trend ?? null, aic, converged, iterations, visited, agreement }
}

/** Validates the `data` payload of the `aic_grid` artifact (contract.md section 3.6). */
export function parseAicGrid(data: unknown): AicGridResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  const sample = r.literal(r.field(data, 'sample', 'data'), 'train', 'data.sample')
  const nTrain = r.int(r.field(data, 'n_train', 'data'), 'data.n_train', 1)
  const criterion = r.literal(r.field(data, 'criterion', 'data'), 'aic', 'data.criterion')

  let ps: number[] | undefined
  let qs: number[] | undefined
  let specs: { d: number; trends: TrendCode[] }[] | undefined
  const gridRaw = r.field(data, 'grid', 'data')
  if (gridRaw !== MISSING) {
    const gd = r.obj(gridRaw, 'data.grid')
    if (gd) {
      ps = axis(r, r.field(gd, 'p', 'data.grid'), 'data.grid.p')
      qs = axis(r, r.field(gd, 'q', 'data.grid'), 'data.grid.q')
      const rawSpecs = r.arr(r.field(gd, 'specs', 'data.grid'), 'data.grid.specs')
      if (rawSpecs) {
        const out: { d: number; trends: TrendCode[] }[] = []
        const start = r.errors.length
        if (rawSpecs.length === 0) r.errors.push('data.grid.specs: must not be empty')
        rawSpecs.forEach((item, i) => {
          const at = `data.grid.specs[${i}]`
          const sp = r.obj(item, at)
          if (!sp) return
          const d = r.int(r.field(sp, 'd', at), `${at}.d`)
          const trends = r.arr(r.field(sp, 'trends', at), `${at}.trends`)
          const codes = (trends ?? []).map((t, j) => r.choice(t, TREND_CODES, `${at}.trends[${j}]`))
          if (trends && (codes.length === 0 || codes.some((c) => !c) || codes.some((c, j) => j > 0 && (c as string) <= (codes[j - 1] as string)))) {
            r.errors.push(`${at}.trends: must be a non-empty list of trend codes in alphabetical order, got ${show(trends)}`)
          }
          if (d !== undefined && out.length > 0 && d <= out[out.length - 1].d) r.errors.push(`${at}.d: ${d} does not come after ${out[out.length - 1].d}; specs are sorted by d`)
          if (d !== undefined && trends) out.push({ d, trends: codes.filter((c): c is TrendCode => !!c) })
        })
        specs = r.errors.length === start ? out : undefined
      }
    }
  }

  let threshold: number | undefined
  let randomStarts: number | undefined
  let tolerance: number | undefined
  let fitSettings: AicGrid['fit_settings'] | undefined
  const fsRaw = r.field(data, 'fit_settings', 'data')
  if (fsRaw !== MISSING) {
    const fs = r.obj(fsRaw, 'data.fit_settings')
    if (fs) {
      const at = 'data.fit_settings'
      const [library, version, , , optimizer] = (['library', 'version', 'model', 'method', 'optimizer'] as const).map((name) => r.str(r.field(fs, name, at), `${at}.${name}`))
      const maxiter = r.int(r.field(fs, 'maxiter', at), `${at}.maxiter`, 1)
      for (const name of ['enforce_stationarity', 'enforce_invertibility', 'concentrate_scale', 'simple_differencing']) r.bool(r.field(fs, name, at), `${at}.${name}`)
      threshold = r.num(r.field(fs, 'near_unit_root_threshold', at), `${at}.near_unit_root_threshold`)
      if (threshold !== undefined && !(threshold > 0 && threshold <= 1)) {
        r.errors.push(`${at}.near_unit_root_threshold: must be in (0, 1], got ${threshold}`)
        threshold = undefined
      }
      r.str(r.field(fs, 'starts', at), `${at}.starts`)
      randomStarts = r.int(r.field(fs, 'random_starts', at), `${at}.random_starts`, 0)
      r.int(r.field(fs, 'start_seed', at), `${at}.start_seed`, 0)
      const keep = r.num(r.field(fs, 'keep_tolerance', at), `${at}.keep_tolerance`)
      if (keep !== undefined && keep < 0) r.errors.push(`${at}.keep_tolerance: must not be negative, got ${keep}`)
      const stated = r.num(r.field(fs, 'nesting_tolerance', at), `${at}.nesting_tolerance`)
      if (stated !== undefined && stated !== NESTING_TOLERANCE) r.errors.push(`${at}.nesting_tolerance: is ${stated}, but this reader checks nesting at ${NESTING_TOLERANCE}`)
      tolerance = NESTING_TOLERANCE // the reader's own bound, whatever the file says
      if (library && version && optimizer && maxiter !== undefined && threshold !== undefined && randomStarts !== undefined && tolerance !== undefined) {
        fitSettings = { library, version, optimizer, maxiter, near_unit_root_threshold: threshold, random_starts: randomStarts, nesting_tolerance: tolerance }
      }
    }
  }

  let cells: AicCell[] | undefined
  const rawCells = r.arr(r.field(data, 'cells', 'data'), 'data.cells')
  if (rawCells) {
    const parsed = rawCells.map((item, i) => parseCell(r, item, `data.cells[${i}]`, nTrain, threshold))
    if (parsed.every((c) => c !== undefined)) cells = parsed as AicCell[]
  }
  if (cells && specs && ps && qs) {
    const keyOf = (d: number, t: string, p: number, q: number) => JSON.stringify([d, t, p, q])
    const expected: [number, string, number, number][] = []
    for (const { d, trends } of specs) for (const t of trends) for (const p of ps) for (const q of qs) expected.push([d, t, p, q])
    expected.sort((a, b) => {
      for (let i = 0; i < 4; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1
      return 0
    })
    const found = cells.map((c) => keyOf(c.d, c.trend, c.p, c.q))
    const want = expected.map((e) => keyOf(...e))
    if (!sameValues(found, want)) {
      let first = found.findIndex((k, i) => k !== want[i])
      if (first < 0) first = Math.min(found.length, want.length)
      r.errors.push(`data.cells: must be one cell per (d, trend, p, q) of the grid, sorted; ${found.length} cells, the first difference is at index ${first}`)
      cells = undefined
    }
  }
  if (cells && specs && ps && qs) {
    checkStarts(r, cells, specs, ps, qs, randomStarts)
    if (tolerance !== undefined) checkNesting(r, cells, tolerance)
  }
  const best = new Map<number, AicCell | undefined>()
  if (cells && specs) {
    for (const { d } of specs) {
      const top = lowest(cells.filter((c) => c.d === d && c.status === 'ok'), 'aic')
      best.set(d, top)
      cells.forEach((c, i) => {
        if (c.d !== d) return
        const want = c.aic === null || top === undefined ? null : c.aic - (top.aic as number)
        if (c.delta_aic !== want) r.errors.push(`data.cells[${i}].delta_aic: is ${show(c.delta_aic)}, but aic minus the lowest eligible AIC of d = ${d} is ${show(want)}`)
      })
    }
  }

  let selection: AicGrid['selection'] | undefined
  let chosen: { d: number; order: [number, number, number]; trend: TrendCode } | undefined
  const slRaw = r.field(data, 'selection', 'data')
  if (slRaw !== MISSING) {
    const sl = r.obj(slRaw, 'data.selection')
    if (sl) {
      const at = 'data.selection'
      const dSel = r.int(r.field(sl, 'd_selected', at), `${at}.d_selected`)
      const order = triple(r, r.field(sl, 'order', at), `${at}.order`)
      const trend = r.choice(r.field(sl, 'trend', at), TREND_CODES, `${at}.trend`)
      const aic = r.num(r.field(sl, 'aic', at), `${at}.aic`)
      const bic = r.num(r.field(sl, 'bic', at), `${at}.bic`)
      const k = r.int(r.field(sl, 'k_params', at), `${at}.k_params`, 1)
      const rule = r.str(r.field(sl, 'rule', at), `${at}.rule`)
      const within = listOf(r, r.field(sl, 'within_2_aic', at), `${at}.within_2_aic`, NEAR_TIE_FIELDS)
      const bicChoice = fields(r, r.field(sl, 'bic_choice', at), `${at}.bic_choice`, BIC_FIELDS)
      const perDRaw = r.arr(r.field(sl, 'best_per_d', at), `${at}.best_per_d`)
      let perD: { d: number; cell: Record<string, number | string> | null }[] | undefined
      if (perDRaw) {
        const start = r.errors.length
        const out: { d: number; cell: Record<string, number | string> | null }[] = []
        perDRaw.forEach((item, i) => {
          const entry = r.obj(item, `${at}.best_per_d[${i}]`)
          if (!entry) return
          const d = r.int(r.field(entry, 'd', `${at}.best_per_d[${i}]`), `${at}.best_per_d[${i}].d`)
          const raw = r.field(entry, 'cell', `${at}.best_per_d[${i}]`)
          const cell = raw === null || raw === MISSING ? null : (fields(r, raw, `${at}.best_per_d[${i}].cell`, BEST_FIELDS) ?? null)
          if (d !== undefined) out.push({ d, cell })
        })
        perD = r.errors.length === start ? out : undefined
      }
      const counts = listOf(r, r.field(sl, 'status_counts', at), `${at}.status_counts`, COUNT_FIELDS)
      if (order && dSel !== undefined && order[1] !== dSel) r.errors.push(`${at}.order: has d = ${order[1]}, but d_selected is ${dSel}`)
      if (specs && dSel !== undefined && !specs.some((s) => s.d === dSel)) r.errors.push(`${at}.d_selected: ${dSel} is not a d of the grid`)
      else if (cells && specs && dSel !== undefined) {
        const top = best.get(dSel)
        const eligible = cells.filter((c) => c.d === dSel && c.status === 'ok')
        if (!top) r.errors.push(`${at}: no cell with d = ${dSel} is ok, so nothing can be selected`)
        else if (order && trend) {
          if (top.p !== order[0] || top.q !== order[2] || top.trend !== trend) {
            r.errors.push(`${at}: selects (${order[0]}, ${dSel}, ${order[2]}) trend "${trend}", but the lowest eligible AIC is (${top.p}, ${dSel}, ${top.q}) trend "${top.trend}"`)
          } else if (aic !== top.aic || bic !== top.bic || k !== top.k_params) r.errors.push(`${at}: aic, bic or k_params differ from the selected cell's`)
          else chosen = { d: dSel, order, trend }
        }
        if (within && top) {
          const want = eligible
            .filter((c) => (c.aic as number) - (top.aic as number) <= 2.0)
            .sort((a, b) => (before(a, b, 'aic') ? -1 : before(b, a, 'aic') ? 1 : 0))
            .map((c) => [c.p, c.q, c.trend, c.aic, c.delta_aic])
          const got = within.map((w) => [w.p, w.q, w.trend, w.aic, w.delta_aic])
          if (got.length !== want.length || got.some((g, i) => !sameValues(g, want[i]))) r.errors.push(`${at}.within_2_aic: must list every ok cell of d_selected within 2 AIC of the best, with its aic and delta_aic, sorted`)
        }
        if (bicChoice && eligible.length > 0) {
          const topBic = lowest(eligible, 'bic') as AicCell
          if (!sameValues([bicChoice.p, bicChoice.q, bicChoice.trend, bicChoice.aic, bicChoice.bic], [topBic.p, topBic.q, topBic.trend, topBic.aic, topBic.bic])) {
            r.errors.push(`${at}.bic_choice: must be the ok cell of d_selected with the lowest BIC`)
          }
        }
        if (perD) {
          const want = specs.map(({ d }) => {
            const top_d = best.get(d)
            return [d, top_d ? JSON.stringify([top_d.p, top_d.q, top_d.trend, top_d.aic]) : null]
          })
          const got = perD.map((e) => [e.d, e.cell ? JSON.stringify([e.cell.p, e.cell.q, e.cell.trend, e.cell.aic]) : null])
          if (got.length !== want.length || got.some((g, i) => !sameValues(g, want[i]))) r.errors.push(`${at}.best_per_d: must give, for each d of the grid in order, its lowest-AIC ok cell or null`)
        }
        if (counts) {
          const want = specs.map(({ d }) => [d, ...CELL_STATUSES.map((s) => (cells as AicCell[]).filter((c) => c.d === d && c.status === s).length)])
          const got = counts.map((c) => [c.d, ...CELL_STATUSES.map((s) => c[s])])
          if (got.length !== want.length || got.some((g, i) => !sameValues(g, want[i]))) r.errors.push(`${at}.status_counts: must count each status for each d of the grid, in order`)
        }
      }
      if (dSel !== undefined && order && trend && aic !== undefined && bic !== undefined && k !== undefined && rule && within && bicChoice && perD && counts) {
        selection = {
          d_selected: dSel,
          order,
          trend,
          aic,
          bic,
          k_params: k,
          rule,
          within_2_aic: within as unknown as AicGrid['selection']['within_2_aic'],
          bic_choice: bicChoice as unknown as AicGrid['selection']['bic_choice'],
          best_per_d: perD as unknown as AicGrid['selection']['best_per_d'],
          status_counts: counts as unknown as AicGrid['selection']['status_counts'],
        }
      }
    }
  }

  let check: AicGrid['pmdarima_check'] | undefined
  const pcRaw = r.field(data, 'pmdarima_check', 'data')
  if (pcRaw !== MISSING) {
    const pc = r.obj(pcRaw, 'data.pmdarima_check')
    if (pc) {
      const at = 'data.pmdarima_check'
      const status = r.choice(r.field(pc, 'status', at), CHECK_STATUSES, `${at}.status`)
      const reason = r.field(pc, 'reason', at)
      const version = r.field(pc, 'version', at)
      const runsRaw = r.arr(r.field(pc, 'runs', at), `${at}.runs`)
      if (status === 'ok') {
        if (reason !== MISSING && reason !== null) r.errors.push(`${at}.reason: must be null when status is ok, got ${show(reason)}`)
        if (version !== MISSING) r.str(version, `${at}.version`)
        if (runsRaw && runsRaw.length === 0) r.errors.push(`${at}.runs: must not be empty when status is ok`)
      } else if (status === 'unavailable') {
        if (reason !== MISSING) r.str(reason, `${at}.reason`)
        if (version !== MISSING) strOrNull(r, version, `${at}.version`)
        if (runsRaw && runsRaw.length > 0) r.errors.push(`${at}.runs: must be empty when status is unavailable`)
      }
      const runs = (runsRaw ?? []).map((item, i) => parseRun(r, item, `${at}.runs[${i}]`, cells, chosen))
      if (status && runsRaw && runs.every((x) => x !== undefined)) {
        check = { status, reason: typeof reason === 'string' ? reason : null, version: typeof version === 'string' ? version : null, runs: runs as PmdarimaRun[] }
      }
    }
  }
  if (r.errors.length > 0 || !sample || nTrain === undefined || !criterion || !ps || !qs || !specs || !fitSettings || !cells || !selection || !check) return { ok: false, errors: r.errors }
  return { ok: true, aicGrid: { sample, n_train: nTrain, criterion, grid: { p: ps, q: qs, specs }, fit_settings: fitSettings, cells, selection, pmdarima_check: check } }
}

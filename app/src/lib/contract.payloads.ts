/**
 * Payload parsers for the milestone-1 artifacts, `prices` and `eda` (contract.md sections 3.2 and
 * 3.3). They extend `contract.ts` and follow its rules: every problem is collected with a path, the
 * result is a fresh object built from the keys we know, and unknown keys inside `data` are ignored.
 *
 * They live in their own module for one reason: the bundle. `contract.ts` is imported by the main
 * chunk (the meta loader), and a module imported by the main chunk is bundled into it whole. These
 * parsers are used only by the lazily loaded price explorer, so here they travel in its chunk.
 */
import { capped, isRecord, isUtcTimestamp, MAX_LIST, MAX_NAMES, OOS_WINDOW, typeName } from './contract'
import { MISSING, Reader, shown } from './contract.reader'

export const SEGMENTS = ['train', 'test', 'oos'] as const
/** The course window's train share, a project constant (config.TRAIN_FRACTION; payloads.TRAIN_FRACTION): pinned, never read from the file. */
export const TRAIN_FRACTION = 0.9
/**
 * prep.MAX_GAP_DAYS (payloads.OOS_MAX_GAP_DAYS): the producer's coverage rule (prep.check_coverage), applied to
 * the oos rows. The first at most this many calendar days after the out-of-sample window starts, the last at
 * most this many before it ends, and no two consecutive ones further apart, so rows dropped at either end or
 * inside are caught (contract.md 3.2).
 */
export const OOS_MAX_GAP_DAYS = 7
export type Segment = (typeof SEGMENTS)[number]

export interface PriceRow {
  date: string
  close_usd: number
  log_close: number
  segment: Segment
}

export interface SegmentSpan {
  start: string
  end: string
  n: number
}

export interface PriceSource {
  provider: string
  yfinance_version: string
  raw_sha256: string
  raw_rows: number
  downloaded_at: string
  request: { start: string; end_exclusive: string; interval: string; auto_adjust: true }
}

export interface Prices {
  ticker: string
  price_basis: 'adjusted_close'
  source: PriceSource
  fill: { method: 'ffill'; filled_dates: string[] }
  splits: { train_fraction: number; train: SegmentSpan; test: SegmentSpan; oos: SegmentSpan }
  rows: PriceRow[]
}

export interface KdePoint {
  x: number
  density: number
  normal_density: number
}

export interface Kde {
  variable: string
  n: number
  bandwidth_method: string
  bandwidth_factor: number
  bandwidth: number
  points: KdePoint[]
}

export interface DecompositionRow {
  date: string
  observed_log: number
  trend_log: number | null
  seasonal_log: number
  resid_log: number | null
}

export interface EdaSummary {
  n: number
  start: string
  end: string
  close_usd: { min: number; max: number; mean: number; median: number }
  log_return: { n: number; mean: number; std: number; skew: number; excess_kurtosis: number }
}

export interface Eda {
  sample: 'train'
  summary: EdaSummary
  kdes: Kde[]
  decomposition: { model: 'additive'; period: number; rows: DecompositionRow[] }
}

export type PricesResult = { ok: true; prices: Prices } | { ok: false; errors: string[] }
export type EdaResult = { ok: true; eda: Eda } | { ok: false; errors: string[] }

const SHA256 = /^[0-9a-f]{64}$/
/** The KDEs the price explorer draws. `variable` is an open enum, so others are allowed too. */
export const REQUIRED_KDE_VARIABLES = ['log_close', 'log_return'] as const


function parseSpan(r: Reader, v: unknown, at: string): SegmentSpan | undefined {
  const o = r.obj(v, at)
  if (!o) return undefined
  const start = r.date(r.field(o, 'start', at), `${at}.start`)
  const end = r.date(r.field(o, 'end', at), `${at}.end`)
  const n = r.int(r.field(o, 'n', at), `${at}.n`, 1)
  if (start === undefined || end === undefined || n === undefined) return undefined
  if (start > end) {
    r.errors.push(`${at}: start ${start} is after end ${end}`)
    return undefined
  }
  return { start, end, n }
}

function parseSource(r: Reader, v: unknown): PriceSource | undefined {
  const at = 'data.source'
  const o = r.obj(v, at)
  if (!o) return undefined
  const provider = r.str(r.field(o, 'provider', at), `${at}.provider`)
  const yfinance_version = r.str(r.field(o, 'yfinance_version', at), `${at}.yfinance_version`)
  let raw_sha256 = r.str(r.field(o, 'raw_sha256', at), `${at}.raw_sha256`)
  if (raw_sha256 !== undefined && !SHA256.test(raw_sha256)) {
    r.errors.push(`${at}.raw_sha256: ${shown(raw_sha256)} is not 64 lowercase hex characters`)
    raw_sha256 = undefined
  }
  const raw_rows = r.int(r.field(o, 'raw_rows', at), `${at}.raw_rows`, 1)
  let downloaded_at = r.str(r.field(o, 'downloaded_at', at), `${at}.downloaded_at`)
  if (downloaded_at !== undefined && !isUtcTimestamp(downloaded_at)) {
    r.errors.push(`${at}.downloaded_at: ${shown(downloaded_at)} is not a UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)`)
    downloaded_at = undefined
  }
  const rq = r.obj(o.request, `${at}.request`)
  let request: PriceSource['request'] | undefined
  if (rq) {
    const start = r.date(r.field(rq, 'start', `${at}.request`), `${at}.request.start`)
    const end_exclusive = r.date(r.field(rq, 'end_exclusive', `${at}.request`), `${at}.request.end_exclusive`)
    const interval = r.str(r.field(rq, 'interval', `${at}.request`), `${at}.request.interval`)
    const auto_adjust = r.literal(r.field(rq, 'auto_adjust', `${at}.request`), true, `${at}.request.auto_adjust`)
    if (start !== undefined && end_exclusive !== undefined && start >= end_exclusive) {
      r.errors.push(`${at}.request: start ${start} must be before end_exclusive ${end_exclusive}`)
    } else if (start !== undefined && end_exclusive !== undefined && interval !== undefined && auto_adjust !== undefined) {
      request = { start, end_exclusive, interval, auto_adjust }
    }
  }
  if (provider === undefined || yfinance_version === undefined || raw_sha256 === undefined || raw_rows === undefined || downloaded_at === undefined || request === undefined) return undefined
  return { provider, yfinance_version, raw_sha256, raw_rows, downloaded_at, request }
}

/** A row's date and segment, each valid (the split and coverage rules need no more). */
type DatedRow = Pick<PriceRow, 'date' | 'segment'>

/** Days since 0001-01-01 of a valid ISO date, by arithmetic (Hinnant's days_from_civil): Date.UTC reads the years 0-99 as 1900-1999. */
function dayNumber(iso: string): number {
  const [y0, m, d] = [Number(iso.slice(0, 4)), Number(iso.slice(5, 7)), Number(iso.slice(8, 10))]
  const y = m <= 2 ? y0 - 1 : y0
  const era = Math.floor(y / 400)
  const yoe = y - era * 400
  const doy = Math.floor((153 * (m > 2 ? m - 3 : m + 9) + 2) / 5) + d - 1
  return era * 146097 + yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy
}

/**
 * The producer's split (prep.train_size): the course window's first trunc(n x TRAIN_FRACTION) rows are train and
 * the rest test, with the pinned fraction, never the file's. A boundary moved by one row (and the split counts
 * rewritten to match) is refused here; the counts alone could not see it. The same words as payloads.py.
 */
function checkSplitRule(r: Reader, rows: readonly DatedRow[]): void {
  const nTrain = rows.filter((row) => row.segment === 'train').length
  const nTest = rows.filter((row) => row.segment === 'test').length
  const want = Math.trunc((nTrain + nTest) * TRAIN_FRACTION)
  if (nTrain !== want) {
    r.errors.push(`data.rows: ${nTrain} rows are train and ${nTest} test, but the course window's ${nTrain + nTest} rows split at ${TRAIN_FRACTION} give int(${nTrain + nTest} x ${TRAIN_FRACTION}) = ${want} train and ${nTrain + nTest - want} test (prep.train_size)`)
  }
}

/** The producer's coverage rule on the oos rows (OOS_MAX_GAP_DAYS); the same words as payloads.py. */
function checkOosCoverage(r: Reader, rows: readonly DatedRow[]): void {
  const oos = rows.flatMap((row, i) => (row.segment === 'oos' ? [{ i, date: row.date, day: dayNumber(row.date) }] : []))
  if (oos.length === 0) return
  const rule = `more than ${OOS_MAX_GAP_DAYS} (prep.MAX_GAP_DAYS) means rows are missing`
  const first = oos[0]
  const last = oos[oos.length - 1]
  const afterStart = first.day - dayNumber(OOS_WINDOW.start)
  if (afterStart > OOS_MAX_GAP_DAYS) r.errors.push(`data.rows[${first.i}].date: the first oos row is ${first.date}, ${afterStart} calendar days after the out-of-sample window starts on ${OOS_WINDOW.start}; ${rule}`)
  const beforeEnd = dayNumber(OOS_WINDOW.end_exclusive) - last.day
  if (beforeEnd > OOS_MAX_GAP_DAYS) r.errors.push(`data.rows[${last.i}].date: the last oos row is ${last.date}, ${beforeEnd} calendar days before the out-of-sample window ends on ${OOS_WINDOW.end_exclusive} (exclusive); ${rule}`)
  oos.slice(1).forEach((b, k) => {
    const gap = b.day - oos[k].day
    if (gap > OOS_MAX_GAP_DAYS) r.errors.push(`data.rows[${b.i}].date: ${b.date} is ${gap} calendar days after the oos row before it, ${oos[k].date}; ${rule}`)
  })
}

function parsePriceRows(r: Reader, v: unknown): PriceRow[] | undefined {
  const list = r.list(v, 'data.rows', MAX_LIST, 'rows')
  if (!list) return undefined
  if (list.length === 0) {
    r.errors.push('data.rows: must not be empty')
    return undefined
  }
  const before = r.errors.length
  const rows: PriceRow[] = []
  const dated: DatedRow[] = []
  let lastDate = ''
  let lastRank = -1
  list.forEach((item, i) => {
    const at = `data.rows[${i}]`
    const o = r.obj(item, at)
    if (!o) return
    const date = r.date(r.field(o, 'date', at), `${at}.date`)
    let close_usd = r.num(r.field(o, 'close_usd', at), `${at}.close_usd`)
    if (close_usd !== undefined && close_usd <= 0) {
      r.errors.push(`${at}.close_usd: must be positive, got ${close_usd}`)
      close_usd = undefined
    }
    const log_close = r.num(r.field(o, 'log_close', at), `${at}.log_close`)
    const seg = r.field(o, 'segment', at)
    let segment: Segment | undefined
    if (seg !== MISSING) {
      if ((SEGMENTS as readonly unknown[]).includes(seg)) segment = seg as Segment
      else r.errors.push(`${at}.segment: expected one of ${SEGMENTS.join(', ')}, got ${shown(seg)}`)
    }
    if (date !== undefined) {
      // ISO dates order as strings, so "not after the previous date" is a string comparison.
      if (date <= lastDate) r.errors.push(`${at}.date: ${date} does not come after ${lastDate}`)
      lastDate = date
    }
    if (segment !== undefined) {
      const rank = SEGMENTS.indexOf(segment)
      if (rank < lastRank) r.errors.push(`${at}.segment: ${shown(segment)} after a later segment; expected train, then test, then oos`)
      lastRank = Math.max(lastRank, rank)
    }
    if (date !== undefined && segment !== undefined) dated.push({ date, segment })
    if (date !== undefined && close_usd !== undefined && log_close !== undefined && segment !== undefined) rows.push({ date, close_usd, log_close, segment })
  })
  if (dated.length === list.length) {
    // Every row's date and segment valid: the producer's split and coverage rules, as payloads.py.
    checkSplitRule(r, dated)
    checkOosCoverage(r, dated)
  }
  return r.errors.length > before ? undefined : rows
}

/** Validates the `data` payload of the `prices` artifact (contract.md section 3.2). */
export function parsePrices(data: unknown): PricesResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  return capped(r.errors, 'data', () => readPrices(r, data))
}

/** parsePrices's body, stopped by `capped` at MAX_PROBLEMS problems. */
function readPrices(r: Reader, data: Record<string, unknown>): PricesResult {
  const ticker = r.str(r.field(data, 'ticker', 'data'), 'data.ticker')
  const price_basis = r.literal(r.field(data, 'price_basis', 'data'), 'adjusted_close', 'data.price_basis')
  const source = Object.hasOwn(data, 'source') ? parseSource(r, data.source) : (r.errors.push('data.source: missing'), undefined)
  const rows = parsePriceRows(r, r.field(data, 'rows', 'data'))

  let fill: Prices['fill'] | undefined
  const fo = Object.hasOwn(data, 'fill') ? r.obj(data.fill, 'data.fill') : (r.errors.push('data.fill: missing'), undefined)
  if (fo) {
    const method = r.literal(r.field(fo, 'method', 'data.fill'), 'ffill', 'data.fill.method')
    const list = r.list(r.field(fo, 'filled_dates', 'data.fill'), 'data.fill.filled_dates', MAX_LIST, 'dates')
    if (list) {
      const before = r.errors.length
      const dates = list.map((d, i) => r.date(d, `data.fill.filled_dates[${i}]`))
      const known = rows ? new Set(rows.map((row) => row.date)) : undefined
      dates.forEach((d, i) => {
        if (d === undefined) return
        const prev = dates[i - 1]
        if (i > 0 && prev !== undefined && d <= prev) r.errors.push(`data.fill.filled_dates[${i}]: dates must be sorted and unique`)
        if (known && !known.has(d)) r.errors.push(`data.fill.filled_dates[${i}]: ${d} is not one of the rows`)
      })
      if (method !== undefined && r.errors.length === before) fill = { method, filled_dates: dates as string[] }
    }
  }

  let splits: Prices['splits'] | undefined
  const so = Object.hasOwn(data, 'splits') ? r.obj(data.splits, 'data.splits') : (r.errors.push('data.splits: missing'), undefined)
  if (so) {
    let fraction = r.num(r.field(so, 'train_fraction', 'data.splits'), 'data.splits.train_fraction')
    if (fraction !== undefined && !(fraction > 0 && fraction < 1)) {
      r.errors.push(`data.splits.train_fraction: must be between 0 and 1, got ${fraction}`)
      fraction = undefined
    } else if (fraction !== undefined && fraction !== TRAIN_FRACTION) {
      r.errors.push(`data.splits.train_fraction: is ${fraction}, but this reader splits the course window at ${TRAIN_FRACTION}`)
      fraction = undefined
    }
    const spans = SEGMENTS.map((name) => parseSpan(r, so[name], `data.splits.${name}`))
    // The pinned out-of-sample window: the oos segment inside it, train and test before it (ISO dates compare as strings).
    SEGMENTS.forEach((name, k) => {
      const span = spans[k]
      if (!span) return
      if (name === 'oos' && !(OOS_WINDOW.start <= span.start && span.end < OOS_WINDOW.end_exclusive)) {
        r.errors.push(`data.splits.oos: runs ${span.start} to ${span.end}, but this reader's out-of-sample window is ${OOS_WINDOW.start} to ${OOS_WINDOW.end_exclusive} (exclusive)`)
      }
      if (name !== 'oos' && !(span.end < OOS_WINDOW.start)) r.errors.push(`data.splits.${name}.end: is ${span.end}, but the ${name} rows come before the out-of-sample window, which starts ${OOS_WINDOW.start}`)
    })
    if (rows) {
      // The spans must describe the rows: the same count, first and last date per segment.
      SEGMENTS.forEach((name, k) => {
        const span = spans[k]
        const mine = rows.filter((row) => row.segment === name)
        if (!span) return
        if (span.n !== mine.length) r.errors.push(`data.splits.${name}.n: says ${span.n}, but ${mine.length} rows have segment "${name}"`)
        else if (span.start !== mine[0].date || span.end !== mine[mine.length - 1].date) {
          r.errors.push(`data.splits.${name}: says ${span.start} to ${span.end}, but the rows run ${mine[0].date} to ${mine[mine.length - 1].date}`)
        }
      })
    }
    const [train, test, oos] = spans
    if (fraction !== undefined && train && test && oos) splits = { train_fraction: fraction, train, test, oos }
  }

  if (r.errors.length > 0 || !ticker || !price_basis || !source || !rows || !fill || !splits) return { ok: false, errors: r.errors }
  return { ok: true, prices: { ticker, price_basis, source, fill, splits, rows } }
}

function parseKde(r: Reader, v: unknown, at: string): Kde | undefined {
  const o = r.obj(v, at)
  if (!o) return undefined
  const before = r.errors.length
  const variable = r.str(r.field(o, 'variable', at), `${at}.variable`)
  const n = r.int(r.field(o, 'n', at), `${at}.n`, 2)
  const bandwidth_method = r.str(r.field(o, 'bandwidth_method', at), `${at}.bandwidth_method`)
  const positive = (key: string) => {
    const x = r.num(r.field(o, key, at), `${at}.${key}`)
    if (x !== undefined && x <= 0) r.errors.push(`${at}.${key}: must be positive, got ${x}`)
    return x !== undefined && x > 0 ? x : undefined
  }
  const bandwidth_factor = positive('bandwidth_factor')
  const bandwidth = positive('bandwidth')
  const list = r.list(r.field(o, 'points', at), `${at}.points`, MAX_LIST, 'points')
  const points: KdePoint[] = []
  if (list) {
    if (list.length < 2) r.errors.push(`${at}.points: expected at least 2 points, got ${list.length}`)
    let lastX = -Infinity
    list.forEach((item, i) => {
      const pat = `${at}.points[${i}]`
      const p = r.obj(item, pat)
      if (!p) return
      const x = r.num(r.field(p, 'x', pat), `${pat}.x`)
      const nonNegative = (key: string) => {
        const d = r.num(r.field(p, key, pat), `${pat}.${key}`)
        if (d !== undefined && d < 0) r.errors.push(`${pat}.${key}: must not be negative, got ${d}`)
        return d
      }
      const density = nonNegative('density')
      const normal_density = nonNegative('normal_density')
      if (x !== undefined) {
        if (x <= lastX) r.errors.push(`${pat}.x: ${x} does not come after ${lastX}`)
        lastX = x
      }
      if (x !== undefined && density !== undefined && normal_density !== undefined) points.push({ x, density, normal_density })
    })
  }
  if (r.errors.length > before || !variable || n === undefined || !bandwidth_method || bandwidth_factor === undefined || bandwidth === undefined || !list) return undefined
  return { variable, n, bandwidth_method, bandwidth_factor, bandwidth, points }
}

function parseSummary(r: Reader, v: unknown): EdaSummary | undefined {
  const at = 'data.summary'
  const o = r.obj(v, at)
  if (!o) return undefined
  const before = r.errors.length
  const n = r.int(r.field(o, 'n', at), `${at}.n`, 2)
  const start = r.date(r.field(o, 'start', at), `${at}.start`)
  const end = r.date(r.field(o, 'end', at), `${at}.end`)
  if (start !== undefined && end !== undefined && start >= end) r.errors.push(`${at}: start ${start} must be before end ${end}`)
  const numbers = <K extends string>(key: string, names: readonly K[]): Record<K, number> | undefined => {
    const inner = r.obj(o[key], `${at}.${key}`)
    if (!inner) return undefined
    const out = {} as Record<K, number>
    let ok = true
    for (const name of names) {
      const x = r.num(r.field(inner, name, `${at}.${key}`), `${at}.${key}.${name}`)
      if (x === undefined) ok = false
      else out[name] = x
    }
    return ok ? out : undefined
  }
  const close_usd = numbers('close_usd', ['min', 'max', 'mean', 'median'] as const)
  const lr = r.obj(o.log_return, `${at}.log_return`)
  const lrN = lr ? r.int(r.field(lr, 'n', `${at}.log_return`), `${at}.log_return.n`, 1) : undefined
  const moments = numbers('log_return', ['mean', 'std', 'skew', 'excess_kurtosis'] as const)
  // n prices give n - 1 daily returns (contract.md section 3.3).
  if (n !== undefined && lrN !== undefined && lrN !== n - 1) r.errors.push(`${at}.log_return.n: is ${lrN}, but data.summary.n - 1 is ${n - 1}`)
  if (r.errors.length > before || n === undefined || !start || !end || !close_usd || lrN === undefined || !moments) return undefined
  return { n, start, end, close_usd, log_return: { n: lrN, ...moments } }
}

function parseDecomposition(r: Reader, v: unknown, summary: EdaSummary | undefined): Eda['decomposition'] | undefined {
  const at = 'data.decomposition'
  const o = r.obj(v, at)
  if (!o) return undefined
  const before = r.errors.length
  const model = r.literal(r.field(o, 'model', at), 'additive', `${at}.model`)
  const period = r.int(r.field(o, 'period', at), `${at}.period`, 2)
  const list = r.list(r.field(o, 'rows', at), `${at}.rows`, MAX_LIST, 'rows')
  const rows: DecompositionRow[] = []
  if (list) {
    let lastDate = ''
    list.forEach((item, i) => {
      const rat = `${at}.rows[${i}]`
      const row = r.obj(item, rat)
      if (!row) return
      const date = r.date(r.field(row, 'date', rat), `${rat}.date`)
      const observed_log = r.num(r.field(row, 'observed_log', rat), `${rat}.observed_log`)
      const seasonal_log = r.num(r.field(row, 'seasonal_log', rat), `${rat}.seasonal_log`)
      const trend_log = r.numOrNull(r.field(row, 'trend_log', rat), `${rat}.trend_log`)
      const resid_log = r.numOrNull(r.field(row, 'resid_log', rat), `${rat}.resid_log`)
      if (trend_log !== undefined && resid_log !== undefined && (trend_log === null) !== (resid_log === null)) {
        r.errors.push(`${rat}: trend_log and resid_log must be null on the same rows`)
      }
      if (date !== undefined) {
        if (date <= lastDate) r.errors.push(`${rat}.date: ${date} does not come after ${lastDate}`)
        lastDate = date
      }
      if (date !== undefined && observed_log !== undefined && seasonal_log !== undefined && trend_log !== undefined && resid_log !== undefined) {
        rows.push({ date, observed_log, trend_log, seasonal_log, resid_log })
      }
    })
    // The centred moving average is undefined for exactly period // 2 rows at each end, and nowhere else.
    if (period !== undefined && r.errors.length === before) {
      const half = Math.floor(period / 2)
      const wrong = rows.findIndex((row, i) => (row.trend_log === null) !== (i < half || i >= rows.length - half))
      if (wrong >= 0) r.errors.push(`${at}.rows: trend_log must be null on exactly the first and last ${half} rows (period ${period} // 2), and nowhere else; row ${wrong} breaks this`)
    }
    if (summary && r.errors.length === before && (rows.length !== summary.n || rows[0]?.date !== summary.start || rows[rows.length - 1]?.date !== summary.end)) {
      r.errors.push(`${at}.rows: ${rows.length} rows from ${rows[0]?.date} to ${rows[rows.length - 1]?.date}, but the summary covers ${summary.n} rows from ${summary.start} to ${summary.end}`)
    }
  }
  if (r.errors.length > before || !model || period === undefined || !list) return undefined
  return { model, period, rows }
}

/** Validates the `data` payload of the `eda` artifact (contract.md section 3.3). */
export function parseEda(data: unknown): EdaResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const r = new Reader()
  return capped(r.errors, 'data', () => readEda(r, data))
}

/** parseEda's body, stopped by `capped` at MAX_PROBLEMS problems. */
function readEda(r: Reader, data: Record<string, unknown>): EdaResult {
  const sample = r.literal(r.field(data, 'sample', 'data'), 'train', 'data.sample')
  const summary = Object.hasOwn(data, 'summary') ? parseSummary(r, data.summary) : (r.errors.push('data.summary: missing'), undefined)
  const list = r.list(r.field(data, 'kdes', 'data'), 'data.kdes', MAX_NAMES, 'KDEs')
  let kdes: Kde[] | undefined
  if (list) {
    const before = r.errors.length
    const parsed = list.map((k, i) => parseKde(r, k, `data.kdes[${i}]`))
    // Read the names from the raw entries, so one broken KDE does not also report "no KDE for ...".
    const variables = list.flatMap((k) => (isRecord(k) && typeof k.variable === 'string' ? [k.variable] : []))
    for (const required of REQUIRED_KDE_VARIABLES) {
      if (!variables.includes(required)) r.errors.push(`data.kdes: no KDE for "${required}"`)
    }
    const twice = variables.find((v, i) => variables.indexOf(v) !== i)
    if (twice !== undefined) r.errors.push(`data.kdes: duplicate variables: ${shown(twice)} appears more than once`)
    if (r.errors.length === before) kdes = parsed as Kde[]
  }
  const decomposition = Object.hasOwn(data, 'decomposition') ? parseDecomposition(r, data.decomposition, summary) : (r.errors.push('data.decomposition: missing'), undefined)
  if (r.errors.length > 0 || !sample || !summary || !kdes || !decomposition) return { ok: false, errors: r.errors }
  return { ok: true, eda: { sample, summary, kdes, decomposition } }
}

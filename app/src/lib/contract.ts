/**
 * The JSON contract between `tools/export_app_data.py` and this app.
 *
 * Every file `public/data/<artifact>.json` is an envelope:
 *   { schema_version, artifact, generated_at, source_commit, data }
 * The parsers here are pure: no fetch, no clock, no DOM. They collect every problem they find
 * (not just the first) so a broken export can be fixed in one pass.
 *
 * Compatibility rule: the app refuses any schema major version other than SUPPORTED_MAJOR and
 * accepts every 1.x.y. The envelope's top level is closed: exactly the five keys above, and an
 * unknown top-level key is an error, as it is in contract.py. Adding an envelope field is
 * therefore a major bump. The `data` object is open: because a minor release may add fields to a
 * payload, unknown keys inside `data` are ignored (a tolerant reader); missing or wrongly typed
 * known keys are errors.
 *
 * These rules are written twice, here and in `src/arima_forecasting/contract.py`.
 * `src/test/fixtures/envelope_cases.json` is the one list of envelopes and verdicts that both
 * languages' tests run, which is what keeps the two copies identical.
 */

export const SUPPORTED_MAJOR = 1

export const MILESTONE_STATUSES = ['done', 'current', 'planned'] as const
export type MilestoneStatus = (typeof MILESTONE_STATUSES)[number]

export interface Envelope {
  schema_version: string
  artifact: string
  generated_at: string
  source_commit: string
  data: Record<string, unknown>
}

export interface DateWindow {
  start: string
  end_exclusive: string
}

export interface Milestone {
  id: number
  slug: string
  title: string
  status: MilestoneStatus
}

export interface Meta {
  project: string
  title: string
  ticker: string
  windows: { course: DateWindow; oos: DateWindow }
  milestones: Milestone[]
  artifacts: string[]
  /**
   * Artifacts the export wrote that the repository does not commit (the owner gate in ADR-0001),
   * so a fresh clone lacks them. Added in 1.1.0; a 1.0.x file has no such key and reads as [].
   */
  held_artifacts: string[]
}

export type EnvelopeResult = { ok: true; envelope: Envelope } | { ok: false; errors: string[] }
export type MetaResult = { ok: true; meta: Meta } | { ok: false; errors: string[] }

const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
const UTC_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$/
// A SHA-1 repository has 40 hex characters per commit id, a SHA-256 repository 64.
const COMMIT = /^(?:[0-9a-f]{40}|[0-9a-f]{64})(-dirty)?$/
// JS "$" (without the m flag) matches only at the very end, so "meta\n" is rejected; Python's
// "$" would accept it, which is why contract.py uses fullmatch().
const ARTIFACT = /^[a-z][a-z0-9_]*$/
const ENVELOPE_KEYS = ['schema_version', 'artifact', 'generated_at', 'source_commit', 'data'] as const

/**
 * A string made only of these characters counts as empty. The same class is written in
 * src/arima_forecasting/payloads.py: the union of what JavaScript's trim and Python's str.strip
 * remove (trim strips U+FEFF, strip does not; strip removes U+001C-U+001F and U+0085, trim does
 * not), so neither reader accepts a value the other calls blank. Shared with the payload parsers.
 */
// eslint-disable-next-line no-control-regex -- U+001C-U+001F are listed on purpose: Python's strip removes them
export const BLANK = /^[\t\n\v\f\r \u001c-\u001f\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]*$/

/** A plain JSON object (not null, not an array). Shared with the payload parsers. */
export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/** The JSON type of a value, for error messages. Shared with the payload parsers. */
export function typeName(v: unknown): string {
  if (v === null) return 'null'
  if (Array.isArray(v)) return 'array'
  return typeof v
}

const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

/** Gregorian leap-year rule: every 4th year, except every 100th, except every 400th. */
function isLeapYear(y: number): boolean {
  return y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)
}

/**
 * True when y-m-d names a real day of the Gregorian calendar, years 0001-9999 (what Python's
 * `datetime` accepts: year 0000 is refused). Plain arithmetic on purpose: `Date.UTC` reads the
 * years 0-99 as 1900-1999, so a Date-based check wrongly rejects every day in 0001-0099. The
 * callers' regexes guarantee four digits, so y <= 9999 needs no check here.
 */
function isCalendarDay(y: number, m: number, d: number): boolean {
  if (y < 1 || m < 1 || m > 12 || d < 1) return false
  return d <= (m === 2 && isLeapYear(y) ? 29 : DAYS_IN_MONTH[m - 1])
}

export function isIsoDate(s: string): boolean {
  const m = ISO_DATE.exec(s)
  return m !== null && isCalendarDay(Number(m[1]), Number(m[2]), Number(m[3]))
}

/** UTC `YYYY-MM-DDTHH:MM:SSZ`, a real instant (no offsets, no fractions, no leap second). */
export function isUtcTimestamp(s: string): boolean {
  const m = UTC_TIMESTAMP.exec(s)
  if (m === null) return false
  const [h, mi, sec] = [Number(m[4]), Number(m[5]), Number(m[6])]
  return isCalendarDay(Number(m[1]), Number(m[2]), Number(m[3])) && h <= 23 && mi <= 59 && sec <= 59
}

export function isSourceCommit(s: string): boolean {
  return s === 'uncommitted' || COMMIT.test(s)
}

/** Reads `obj[key]` as a string; records an error and returns undefined if absent or mistyped. */
function readString(obj: Record<string, unknown>, key: string, path: string, errors: string[], opts: { nonEmpty?: boolean } = {}): string | undefined {
  const at = path ? `${path}.${key}` : key
  if (!Object.hasOwn(obj, key)) {
    errors.push(`${at}: missing`)
    return undefined
  }
  const v = obj[key]
  if (typeof v !== 'string') {
    errors.push(`${at}: expected a string, got ${typeName(v)}`)
    return undefined
  }
  if (opts.nonEmpty && BLANK.test(v)) {
    errors.push(`${at}: must not be empty`)
    return undefined
  }
  return v
}

export function parseEnvelope(raw: unknown): EnvelopeResult {
  if (!isRecord(raw)) return { ok: false, errors: [`envelope: expected an object, got ${typeName(raw)}`] }
  const errors: string[] = []

  const schemaVersion = readString(raw, 'schema_version', '', errors)
  if (schemaVersion !== undefined) {
    const m = SEMVER.exec(schemaVersion)
    if (m === null) {
      errors.push(`schema_version: "${schemaVersion}" is not a semantic version (MAJOR.MINOR.PATCH)`)
    } else if (Number(m[1]) !== SUPPORTED_MAJOR) {
      errors.push(`schema_version: major version ${m[1]} is not supported (this app reads ${SUPPORTED_MAJOR}.x.y)`)
    }
  }

  const artifact = readString(raw, 'artifact', '', errors)
  if (artifact !== undefined && !ARTIFACT.test(artifact)) {
    errors.push(`artifact: "${artifact}" must match [a-z][a-z0-9_]*`)
  }

  const generatedAt = readString(raw, 'generated_at', '', errors)
  if (generatedAt !== undefined && !isUtcTimestamp(generatedAt)) {
    errors.push(`generated_at: "${generatedAt}" is not a UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)`)
  }

  const sourceCommit = readString(raw, 'source_commit', '', errors)
  if (sourceCommit !== undefined && !isSourceCommit(sourceCommit)) {
    errors.push(`source_commit: "${sourceCommit}" is not <40 or 64 hex>, <40 or 64 hex>-dirty or "uncommitted"`)
  }

  let data: Record<string, unknown> | undefined
  if (!Object.hasOwn(raw, 'data')) errors.push('data: missing')
  else if (!isRecord(raw.data)) errors.push(`data: expected an object, got ${typeName(raw.data)}`)
  else data = raw.data

  // The top level is closed. Object.keys lists own keys only: a key that the JSON calls
  // "__proto__" or "constructor" is an own key and is reported like any other, while anything
  // inherited through the prototype chain was never in the file.
  for (const key of Object.keys(raw)) {
    if (!(ENVELOPE_KEYS as readonly string[]).includes(key)) errors.push(`${key}: unexpected key`)
  }

  if (errors.length > 0 || schemaVersion === undefined || artifact === undefined || generatedAt === undefined || sourceCommit === undefined || data === undefined) {
    return { ok: false, errors }
  }
  return {
    ok: true,
    envelope: { schema_version: schemaVersion, artifact, generated_at: generatedAt, source_commit: sourceCommit, data },
  }
}

function parseWindow(raw: unknown, path: string, errors: string[]): DateWindow | undefined {
  if (!isRecord(raw)) {
    errors.push(`${path}: ${raw === undefined ? 'missing' : `expected an object, got ${typeName(raw)}`}`)
    return undefined
  }
  const before = errors.length
  const start = readString(raw, 'start', path, errors)
  const end = readString(raw, 'end_exclusive', path, errors)
  if (start !== undefined && !isIsoDate(start)) errors.push(`${path}.start: "${start}" is not a calendar date (YYYY-MM-DD)`)
  if (end !== undefined && !isIsoDate(end)) errors.push(`${path}.end_exclusive: "${end}" is not a calendar date (YYYY-MM-DD)`)
  if (errors.length > before || start === undefined || end === undefined) return undefined
  // ISO dates order lexicographically
  if (start >= end) {
    errors.push(`${path}: start ${start} must be before end_exclusive ${end}`)
    return undefined
  }
  return { start, end_exclusive: end }
}

function parseMilestone(raw: unknown, path: string, seenIds: Set<number>, errors: string[]): Milestone | undefined {
  if (!isRecord(raw)) {
    errors.push(`${path}: expected an object, got ${typeName(raw)}`)
    return undefined
  }
  const before = errors.length
  let id: number | undefined
  if (!Object.hasOwn(raw, 'id')) errors.push(`${path}.id: missing`)
  else if (typeof raw.id !== 'number' || !Number.isSafeInteger(raw.id) || raw.id < 0) errors.push(`${path}.id: expected a non-negative integer, got ${JSON.stringify(raw.id)}`)
  else if (seenIds.has(raw.id)) errors.push(`${path}.id: duplicate id ${raw.id}`)
  else {
    id = raw.id
    seenIds.add(id)
  }
  const slug = readString(raw, 'slug', path, errors, { nonEmpty: true })
  const title = readString(raw, 'title', path, errors, { nonEmpty: true })
  const status = readString(raw, 'status', path, errors)
  if (status !== undefined && !(MILESTONE_STATUSES as readonly string[]).includes(status)) {
    errors.push(`${path}.status: expected one of ${MILESTONE_STATUSES.join(', ')}, got "${status}"`)
  }
  if (errors.length > before || id === undefined || slug === undefined || title === undefined || status === undefined) return undefined
  return { id, slug, title, status: status as MilestoneStatus }
}

/** Validates the `data` payload of the `meta` artifact. Same Result style as parseEnvelope. */
export function parseMeta(data: unknown): MetaResult {
  if (!isRecord(data)) return { ok: false, errors: [`data: expected an object, got ${typeName(data)}`] }
  const errors: string[] = []

  const project = readString(data, 'project', 'data', errors, { nonEmpty: true })
  const title = readString(data, 'title', 'data', errors, { nonEmpty: true })
  const ticker = readString(data, 'ticker', 'data', errors, { nonEmpty: true })

  let course: DateWindow | undefined
  let oos: DateWindow | undefined
  if (!Object.hasOwn(data, 'windows')) errors.push('data.windows: missing')
  else if (!isRecord(data.windows)) errors.push(`data.windows: expected an object, got ${typeName(data.windows)}`)
  else {
    course = parseWindow(data.windows.course, 'data.windows.course', errors)
    oos = parseWindow(data.windows.oos, 'data.windows.oos', errors)
  }

  let milestones: Milestone[] | undefined
  if (!Object.hasOwn(data, 'milestones')) errors.push('data.milestones: missing')
  else if (!Array.isArray(data.milestones)) errors.push(`data.milestones: expected an array, got ${typeName(data.milestones)}`)
  else {
    const seenIds = new Set<number>()
    const parsed = data.milestones.map((m, i) => parseMilestone(m, `data.milestones[${i}]`, seenIds, errors))
    milestones = parsed.filter((m): m is Milestone => m !== undefined)
    if (milestones.length !== parsed.length) milestones = undefined
    else {
      // The contract says exactly one milestone is "current" (the progress bar points at it).
      // Checked only once every milestone parsed, so one bad status does not add a second error.
      const current = milestones.filter((m) => m.status === 'current').map((m) => m.id)
      if (current.length !== 1) {
        errors.push(`data.milestones: expected exactly one "current" milestone, found ${current.length === 0 ? 'none' : `${current.length} (ids ${current.join(', ')})`}`)
        milestones = undefined
      }
    }
  }

  let artifacts: string[] | undefined
  if (!Object.hasOwn(data, 'artifacts')) errors.push('data.artifacts: missing')
  else if (!Array.isArray(data.artifacts)) errors.push(`data.artifacts: expected an array, got ${typeName(data.artifacts)}`)
  else {
    const bad = data.artifacts.findIndex((a) => typeof a !== 'string' || BLANK.test(a))
    if (bad >= 0) errors.push(`data.artifacts[${bad}]: expected a non-empty string, got ${JSON.stringify(data.artifacts[bad])}`)
    else artifacts = data.artifacts as string[]
  }

  let held: string[] | undefined = []
  if (Object.hasOwn(data, 'held_artifacts')) {
    if (!Array.isArray(data.held_artifacts)) {
      errors.push(`data.held_artifacts: expected an array, got ${typeName(data.held_artifacts)}`)
      held = undefined
    } else {
      // Each held name is a listed artifact, named once, and never meta itself: the app reads
      // meta.json to learn what is held, so meta cannot be missing on purpose.
      const list = data.held_artifacts
      const bad = list.findIndex((a, i) => typeof a !== 'string' || !(artifacts ?? []).includes(a) || a === 'meta' || list.indexOf(a) !== i)
      if (bad >= 0) {
        errors.push(`data.held_artifacts[${bad}]: ${JSON.stringify(list[bad])} must be a listed artifact other than meta, named once`)
        held = undefined
      } else held = list as string[]
    }
  }

  if (errors.length > 0 || !project || !title || !ticker || !course || !oos || !milestones || !artifacts || !held) return { ok: false, errors }
  return { ok: true, meta: { project, title, ticker, windows: { course, oos }, milestones, artifacts, held_artifacts: held } }
}

import { describe, expect, it } from 'vitest'
import { isIsoDate, isSourceCommit, isUtcTimestamp, MAX_LIST, MAX_NAMES, OOS_WINDOW, parseEnvelope, parseMeta, SUPPORTED_MAJOR, type Meta } from './contract'
import { VALID_COMMIT, validMetaEnvelope, withValue, without, type Json } from '../test/fixtures/fixtures'

const errorsOf = (raw: unknown): string[] => {
  const r = parseEnvelope(raw)
  if (r.ok) throw new Error('expected parseEnvelope to fail')
  return r.errors
}
const metaErrorsOf = (data: unknown): string[] => {
  const r = parseMeta(data)
  if (r.ok) throw new Error('expected parseMeta to fail')
  return r.errors
}
const metaData = (env: Json): unknown => (env as { data: unknown }).data
const SHA256 = '0123456789abcdef'.repeat(4) // 16 hex characters x 4 = 64: a SHA-256 repository's commit id

describe('parseEnvelope: valid input', () => {
  it('accepts the hand-built meta envelope and returns its fields unchanged', () => {
    const raw = validMetaEnvelope() as { data: Record<string, unknown> }
    const r = parseEnvelope(raw)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.envelope.schema_version).toBe('1.0.0')
    expect(r.envelope.artifact).toBe('meta')
    expect(r.envelope.generated_at).toBe('2026-10-28T12:00:00Z')
    expect(r.envelope.source_commit).toBe(VALID_COMMIT)
    expect(r.envelope.data).toEqual(raw.data)
  })
  it('supports major version 1', () => {
    expect(SUPPORTED_MAJOR).toBe(1)
  })
  it.each(['1.0.0', '1.2.3', '1.10.0', '1.0.17'])('accepts every 1.x.y: %s', (v) => {
    expect(parseEnvelope(withValue(['schema_version'], v)).ok).toBe(true)
  })
  it.each([`${'a'.repeat(40)}`, `${VALID_COMMIT}-dirty`, 'uncommitted', SHA256, `${SHA256}-dirty`])('accepts source_commit %s', (c) => {
    expect(parseEnvelope(withValue(['source_commit'], c)).ok).toBe(true)
  })
  it('keeps unknown keys inside data: the payload is open, only the top level is closed', () => {
    const raw = withValue(['data', 'future_field'], { anything: [1, 2, 3] })
    const r = parseEnvelope(raw)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.envelope.data.future_field).toEqual({ anything: [1, 2, 3] })
  })
})

describe('parseEnvelope: the top level is closed', () => {
  it('rejects an unknown top-level key and names it, so a new envelope field needs a major bump', () => {
    expect(errorsOf(withValue(['future_field'], { anything: [1, 2, 3] }))).toEqual(['"future_field": unexpected key']) // a key from the file is quoted (shown)
  })
  it('reports every unknown key, alongside the other problems', () => {
    const raw = withValue(['one'], 1) as Record<string, Json>
    raw.two = 2
    raw.artifact = 'Bad'
    expect(errorsOf(raw)).toEqual(['artifact: "Bad" must match [a-z][a-z0-9_]*', '"one": unexpected key', '"two": unexpected key'])
  })
  it('treats the keys "__proto__" and "constructor" in the JSON as the unknown keys they are', () => {
    // JSON.parse makes "__proto__" an own property; an object literal would set the prototype instead.
    const base = JSON.stringify(validMetaEnvelope()).slice(0, -1)
    expect(errorsOf(JSON.parse(`${base},"__proto__":{}}`))).toEqual(['"__proto__": unexpected key'])
    expect(errorsOf(JSON.parse(`${base},"constructor":"x"}`))).toEqual(['"constructor": unexpected key'])
  })
})

describe('parseEnvelope: schema_version', () => {
  it.each(['2.0.0', '3.1.4', '10.0.0', '0.9.0'])('refuses major %s', (v) => {
    const errs = errorsOf(withValue(['schema_version'], v))
    expect(errs).toHaveLength(1)
    expect(errs[0]).toBe(`schema_version: "${v}" has a major version other than 1 (this app reads 1.x.y)`)
  })
  it.each(['1.0', '1', 'v1.0.0', '1.0.0-rc.1', '1.0.0+build', '01.0.0', '1.00.0', '', ' 1.0.0', '1.0.0 ', '1.x.0'])('rejects non-semver %j', (v) => {
    expect(errorsOf(withValue(['schema_version'], v))).toEqual([`schema_version: "${v}" is not a semantic version (MAJOR.MINOR.PATCH)`])
  })
  it('rejects a number', () => {
    expect(errorsOf(withValue(['schema_version'], 1))).toEqual(['schema_version: expected a string, got number'])
  })
})

describe('parseEnvelope: missing keys', () => {
  it.each(['schema_version', 'artifact', 'generated_at', 'source_commit', 'data'])('reports %s as missing', (key) => {
    expect(errorsOf(without([key]))).toEqual([`${key}: missing`])
  })
  it('does not count inherited properties as present', () => {
    // "constructor" exists on every object via the prototype; a key named like one must not satisfy the check
    const raw = Object.create({ schema_version: '1.0.0' }) as Record<string, Json>
    Object.assign(raw, { artifact: 'meta', generated_at: '2026-10-28T12:00:00Z', source_commit: 'uncommitted', data: {} })
    expect(errorsOf(raw)).toEqual(['schema_version: missing'])
  })
})

describe('parseEnvelope: wrong types and values', () => {
  it('rejects a non-object envelope with a single error', () => {
    for (const bad of [null, [], 'text', 42, true, undefined]) {
      expect(errorsOf(bad)).toHaveLength(1)
      expect(errorsOf(bad)[0]).toMatch(/^envelope: expected an object, got /)
    }
    expect(errorsOf(null)[0]).toBe('envelope: expected an object, got null')
    expect(errorsOf([])[0]).toBe('envelope: expected an object, got array')
  })
  it.each([
    ['artifact', 5, 'artifact: expected a string, got number'],
    ['generated_at', 123, 'generated_at: expected a string, got number'],
    ['source_commit', null, 'source_commit: expected a string, got null'],
  ])('rejects a non-string %s', (key, value, message) => {
    expect(errorsOf(withValue([key], value))).toEqual([message])
  })
  it.each(['', '   ', 'Meta', 'META', '1meta', '_meta', 'meta-2', 'meta.json', 'me ta', ' meta', 'meta\n', 'm\u00e9ta'])('rejects the artifact name %j', (name) => {
    expect(errorsOf(withValue(['artifact'], name))).toEqual([`artifact: ${JSON.stringify(name)} must match [a-z][a-z0-9_]*`])
  })
  it.each(['meta', 'm', 'meta_2', 'a1_', 'price_history'])('accepts the artifact name %j', (name) => {
    expect(parseEnvelope(withValue(['artifact'], name)).ok).toBe(true)
  })
  it.each([
    ['a string', 'meta', 'string'],
    ['an array', [], 'array'],
    ['null', null, 'null'],
    ['a number', 7, 'number'],
  ])('rejects data that is %s', (_label, value, got) => {
    expect(errorsOf(withValue(['data'], value))).toEqual([`data: expected an object, got ${got}`])
  })
})

describe('parseEnvelope: generated_at', () => {
  it.each([
    '2026-10-28 12:00:00Z',
    '2026-10-28T12:00:00',
    '2026-10-28T12:00:00+00:00',
    '2026-10-28T12:00:00.123Z',
    '2026-10-28T12:00Z',
    '2026-10-28',
    '2026-13-01T00:00:00Z',
    '2026-00-10T00:00:00Z',
    '2026-02-30T00:00:00Z',
    '2025-02-29T00:00:00Z',
    '2026-10-32T00:00:00Z',
    '2026-10-28T24:00:00Z',
    '2026-10-28T12:60:00Z',
    '2026-10-28T12:00:60Z',
    '2026-10-28t12:00:00z',
    'yesterday',
    '',
  ])('rejects %j', (ts) => {
    expect(errorsOf(withValue(['generated_at'], ts))).toEqual([`generated_at: "${ts}" is not a UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)`])
  })
  it.each([
    '2024-02-29T23:59:59Z',
    '2026-10-28T00:00:00Z',
    '2026-12-31T23:59:59Z',
    '2000-01-01T00:00:00Z',
    '0001-01-01T00:00:00Z',
    '0050-06-15T12:00:00Z',
    '0099-12-31T23:59:59Z',
    '9999-12-31T23:59:59Z',
  ])('accepts %s', (ts) => {
    expect(parseEnvelope(withValue(['generated_at'], ts)).ok).toBe(true)
  })
  it.each(['0000-01-01T00:00:00Z', '0000-02-29T00:00:00Z', '0100-02-29T00:00:00Z', '1900-02-29T00:00:00Z', '2100-02-29T00:00:00Z'])('rejects %s', (ts) => {
    expect(errorsOf(withValue(['generated_at'], ts))).toEqual([`generated_at: "${ts}" is not a UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)`])
  })
})

describe('parseEnvelope: source_commit', () => {
  const sha = VALID_COMMIT
  it.each([
    'abc1234',
    sha.slice(0, 39),
    `${sha}0`,
    sha.toUpperCase(),
    `${sha}-DIRTY`,
    `${sha}-dirty-extra`,
    `${sha} `,
    `-dirty`,
    'Uncommitted',
    'uncommitted-dirty',
    'g'.repeat(40),
    'a'.repeat(63),
    'a'.repeat(65),
    SHA256.toUpperCase(),
    `${SHA256}-DIRTY`,
    '',
  ])('rejects %j', (c) => {
    expect(errorsOf(withValue(['source_commit'], c))).toEqual([`source_commit: "${c}" is not <40 or 64 hex>, <40 or 64 hex>-dirty or "uncommitted"`])
  })
})

describe('parseEnvelope: error collection', () => {
  it('reports every problem in one pass, not just the first', () => {
    const raw = validMetaEnvelope() as Record<string, Json>
    raw.schema_version = '2.0.0'
    raw.generated_at = 'soon'
    raw.source_commit = 'abc'
    delete raw.artifact
    raw.data = []
    const errs = errorsOf(raw)
    expect(errs).toHaveLength(5)
    expect(errs.join('\n')).toMatch(/schema_version: "2.0.0" has a major version other than 1/)
    expect(errs.join('\n')).toMatch(/artifact: missing/)
    expect(errs.join('\n')).toMatch(/generated_at: "soon"/)
    expect(errs.join('\n')).toMatch(/source_commit: "abc"/)
    expect(errs.join('\n')).toMatch(/data: expected an object, got array/)
  })
})

describe('calendar helpers', () => {
  it('isIsoDate accepts real days, including a leap day, and rejects impossible ones', () => {
    for (const ok of ['2024-02-29', '2015-01-01', '2026-10-01', '2023-12-31']) expect(isIsoDate(ok)).toBe(true)
    for (const bad of ['2023-02-29', '2024-04-31', '2024-00-10', '2024-13-01', '2024-1-1', '24-01-01', '2024-01-01T00:00:00Z', '']) expect(isIsoDate(bad)).toBe(false)
  })
  it('isUtcTimestamp and isSourceCommit are exact-match predicates', () => {
    expect(isUtcTimestamp('2024-02-29T23:59:59Z')).toBe(true)
    expect(isUtcTimestamp('2024-02-29T23:59:59z')).toBe(false)
    expect(isSourceCommit('uncommitted')).toBe(true)
    expect(isSourceCommit('uncommitted ')).toBe(false)
  })
})

describe('calendar arithmetic', () => {
  // The oracle is Date.setUTCFullYear, which (unlike Date.UTC) does not read years 0-99 as 19xx.
  // A day exists when the date comes back unchanged after the Date object normalises it.
  const existsPerDate = (y: number, m: number, d: number): boolean => {
    const t = new Date(0)
    t.setUTCFullYear(y, m - 1, d)
    return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d
  }
  const iso = (y: number, m: number, d: number) => `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`

  it('agrees with the Date oracle on every year 0001-9999 around the end of February and in every month length', () => {
    const wrong: string[] = []
    for (let y = 1; y <= 9999; y++) {
      for (const [m, d] of [[2, 28], [2, 29], [2, 30], [4, 30], [4, 31], [12, 31]]) {
        if (isIsoDate(iso(y, m, d)) !== existsPerDate(y, m, d)) wrong.push(iso(y, m, d))
      }
    }
    expect(wrong).toEqual([])
  })
  it('agrees with the Date oracle on every month and day 00-99 in representative years', () => {
    const wrong: string[] = []
    for (const y of [1, 4, 50, 99, 100, 400, 1900, 2000, 2023, 2024, 2100, 9999]) {
      for (let m = 0; m <= 99; m++) {
        for (let d = 0; d <= 99; d++) {
          if (isIsoDate(iso(y, m, d)) !== existsPerDate(y, m, d)) wrong.push(iso(y, m, d))
        }
      }
    }
    expect(wrong).toEqual([])
  })
  it('refuses year 0000 on every day, as Python datetime does', () => {
    for (const [m, d] of [[1, 1], [2, 29], [12, 31]]) expect(isIsoDate(iso(0, m, d))).toBe(false)
  })
  it('accepts hours 00-23, minutes and seconds 00-59, and nothing else', () => {
    const pad = (n: number) => String(n).padStart(2, '0')
    for (let n = 0; n <= 99; n++) {
      expect(isUtcTimestamp(`2026-10-28T${pad(n)}:00:00Z`)).toBe(n <= 23)
      expect(isUtcTimestamp(`2026-10-28T00:${pad(n)}:00Z`)).toBe(n <= 59)
      expect(isUtcTimestamp(`2026-10-28T00:00:${pad(n)}Z`)).toBe(n <= 59)
    }
  })
})

describe('parseMeta: valid input', () => {
  it('parses the hand-built meta payload into typed fields', () => {
    const r = parseMeta(metaData(validMetaEnvelope()))
    expect(r.ok).toBe(true)
    if (!r.ok) return
    const m: Meta = r.meta
    expect(m.project).toBe('arima-stock-forecasting')
    expect(m.title).toBe('ARIMA stock forecasting, done carefully')
    expect(m.ticker).toBe('AAPL')
    expect(m.windows.course).toEqual({ start: '2015-01-01', end_exclusive: '2024-01-01' })
    expect(m.windows.oos).toEqual({ start: '2024-01-01', end_exclusive: '2026-10-01' })
    expect(m.milestones.map((x) => [x.id, x.slug, x.status])).toEqual([
      [0, 'scaffold', 'current'],
      [1, 'data-eda', 'planned'],
      [2, 'stationarity', 'planned'],
    ])
    expect(m.artifacts).toEqual(['meta'])
  })
  it.each(['done', 'current', 'planned'])('accepts milestone status %s', (status) => {
    const env = withValue(['data', 'milestones', 1, 'status'], status)
    // Keep exactly one "current": when milestone 1 takes it, milestone 0 becomes done.
    if (status === 'current') (env as { data: { milestones: Record<string, Json>[] } }).data.milestones[0].status = 'done'
    const r = parseMeta(metaData(env))
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.meta.milestones[1].status).toBe(status)
  })
  it('accepts an empty artifact list', () => {
    expect(parseMeta(metaData(withValue(['data', 'artifacts'], []))).ok).toBe(true)
  })
  it('ignores unknown extra keys in the payload, a window and a milestone', () => {
    let env = withValue(['data', 'extra'], 1)
    const data = (env as { data: { windows: { course: Record<string, Json> }; milestones: Record<string, Json>[] } }).data
    data.windows.course.note = 'x'
    data.milestones[0].emoji = 'y'
    env = { ...(env as object) } as Json
    const r = parseMeta(metaData(env))
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(Object.keys(r.meta).sort()).toEqual(['artifacts', 'held_artifacts', 'milestones', 'project', 'ticker', 'title', 'windows'])
      expect(Object.keys(r.meta.milestones[0]).sort()).toEqual(['id', 'slug', 'status', 'title'])
    }
  })
})

describe('parseMeta: missing and mistyped keys', () => {
  it.each(['project', 'title', 'ticker', 'windows', 'milestones', 'artifacts'])('reports data.%s as missing', (key) => {
    expect(metaErrorsOf(metaData(without(['data', key])))).toEqual([`data.${key}: missing`])
  })
  it.each([
    ['project', 5, 'data.project: expected a string, got number'],
    ['title', null, 'data.title: expected a string, got null'],
    ['ticker', ['AAPL'], 'data.ticker: expected a string, got array'],
    ['windows', [], 'data.windows: expected an object, got array'],
    ['milestones', {}, 'data.milestones: expected an array, got object'],
    ['artifacts', 'meta', 'data.artifacts: expected an array, got string'],
  ])('rejects a wrongly typed %s', (key, value, message) => {
    expect(metaErrorsOf(metaData(withValue(['data', key], value)))).toEqual([message])
  })
  it('rejects empty strings for project, title and ticker', () => {
    for (const key of ['project', 'title', 'ticker']) {
      expect(metaErrorsOf(metaData(withValue(['data', key], ' ')))).toEqual([`data.${key}: must not be empty`])
    }
  })
  it.each([null, [], 'meta', 3])('rejects a payload that is not an object: %j', (bad) => {
    expect(metaErrorsOf(bad)).toHaveLength(1)
    expect(metaErrorsOf(bad)[0]).toMatch(/^data: expected an object, got /)
  })
})

describe('parseMeta: windows', () => {
  it('reports a missing window and a missing window bound', () => {
    expect(metaErrorsOf(metaData(without(['data', 'windows', 'oos'])))).toEqual(['data.windows.oos: missing'])
    expect(metaErrorsOf(metaData(without(['data', 'windows', 'course', 'start'])))).toEqual(['data.windows.course.start: missing'])
    expect(metaErrorsOf(metaData(without(['data', 'windows', 'course', 'end_exclusive'])))).toEqual(['data.windows.course.end_exclusive: missing'])
  })
  it('rejects a window that is not an object', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'windows', 'course'], '2015')))).toEqual(['data.windows.course: expected an object, got string'])
  })
  it.each(['2024-02-30', '2024-1-1', '2024-01-01T00:00:00Z', 'soon'])('rejects the impossible or malformed date %j', (d) => {
    expect(metaErrorsOf(metaData(withValue(['data', 'windows', 'oos', 'start'], d)))).toEqual([`data.windows.oos.start: "${d}" is not a calendar date (YYYY-MM-DD)`])
    expect(metaErrorsOf(metaData(withValue(['data', 'windows', 'oos', 'end_exclusive'], d)))).toEqual([`data.windows.oos.end_exclusive: "${d}" is not a calendar date (YYYY-MM-DD)`])
  })
  it('rejects a window whose start is not before its exclusive end', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'windows', 'oos', 'end_exclusive'], '2024-01-01')))).toEqual([
      'data.windows.oos: start 2024-01-01 must be before end_exclusive 2024-01-01',
    ])
    expect(metaErrorsOf(metaData(withValue(['data', 'windows', 'oos', 'end_exclusive'], '2023-12-31')))).toEqual([
      'data.windows.oos: start 2024-01-01 must be before end_exclusive 2023-12-31',
    ])
  })
  it('accepts a one-day window', () => {
    expect(parseMeta(metaData(withValue(['data', 'windows', 'course', 'end_exclusive'], '2015-01-02'))).ok).toBe(true)
  })
  it('bounds every list at MAX_LIST (days and points) or MAX_NAMES (names), as payloads.py does', () => {
    expect([MAX_LIST, MAX_NAMES]).toEqual([10_000, 100])
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones'], new Array(101).fill(0))))).toEqual(['data.milestones: has 101 milestones, more than the 100 a reader takes'])
  })
  it('pins the out-of-sample window at 2024-01-01 to 2026-10-01 (exclusive), config.OOS_WINDOW', () => {
    expect(OOS_WINDOW).toEqual({ start: '2024-01-01', end_exclusive: '2026-10-01' })
    const pinned = "but this reader's out-of-sample window is 2024-01-01 to 2026-10-01 (exclusive)"
    expect(metaErrorsOf(metaData(withValue(['data', 'windows', 'oos', 'start'], '2024-01-02')))).toEqual([`data.windows.oos: is 2024-01-02 to 2026-10-01, ${pinned}`])
    expect(metaErrorsOf(metaData(withValue(['data', 'windows', 'oos', 'end_exclusive'], '2026-09-30')))).toEqual([`data.windows.oos: is 2024-01-01 to 2026-09-30, ${pinned}`])
  })
})

describe('parseMeta: milestones and artifacts', () => {
  it('rejects a bad milestone status and names the milestone', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 1, 'status'], 'finished')))).toEqual([
      'data.milestones[1].status: expected one of done, current, planned, got "finished"',
    ])
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 0, 'status'], 'Current')))).toEqual([
      'data.milestones[0].status: expected one of done, current, planned, got "Current"',
    ])
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 2, 'status'], 7)))).toEqual(['data.milestones[2].status: expected a string, got number'])
  })
  it.each([
    ['a string id', '1'],
    ['a negative id', -1],
    ['a fractional id', 1.5],
    ['a null id', null],
  ])('rejects %s', (_label, id) => {
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 1, 'id'], id)))).toEqual([
      `data.milestones[1].id: expected a non-negative integer, got ${JSON.stringify(id)}`,
    ])
  })
  it('rejects a payload with no "current" milestone, including an empty milestone list', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 0, 'status'], 'done')))).toEqual([
      'data.milestones: expected exactly one "current" milestone, found none',
    ])
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones'], [])))).toEqual([
      'data.milestones: expected exactly one "current" milestone, found none',
    ])
  })
  it('rejects two "current" milestones and names their ids', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 2, 'status'], 'current')))).toEqual([
      'data.milestones: expected exactly one "current" milestone, found 2 (ids 0, 2)',
    ])
  })
  it('rejects duplicate milestone ids but allows id 0', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 2, 'id'], 1)))).toEqual(['data.milestones[2].id: duplicate id 1'])
    const r = parseMeta(metaData(validMetaEnvelope()))
    expect(r.ok && r.meta.milestones[0].id).toBe(0)
  })
  it('rejects a milestone that is missing a key or is not an object', () => {
    expect(metaErrorsOf(metaData(without(['data', 'milestones', 0, 'slug'])))).toEqual(['data.milestones[0].slug: missing'])
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 0, 'title'], '')))).toEqual(['data.milestones[0].title: must not be empty'])
    expect(metaErrorsOf(metaData(withValue(['data', 'milestones', 1], 'planned')))).toEqual(['data.milestones[1]: expected an object, got string'])
  })
  it('rejects a bad artifacts entry and names its index', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'artifacts'], ['meta', 3])))).toEqual(['data.artifacts[1]: expected a non-empty string, got 3'])
    expect(metaErrorsOf(metaData(withValue(['data', 'artifacts'], ['meta', ''])))).toEqual(['data.artifacts[1]: expected a non-empty string, got ""'])
  })
  it.each([' ', '   ', '\t', '\n'])('rejects a whitespace-only artifacts entry %j, which is not a name either', (blank) => {
    expect(metaErrorsOf(metaData(withValue(['data', 'artifacts'], ['meta', blank])))).toEqual([
      `data.artifacts[1]: expected a non-empty string, got ${JSON.stringify(blank)}`,
    ])
  })
  it('collects errors from several sections at once', () => {
    let env = withValue(['data', 'ticker'], 5)
    const data = (env as { data: { milestones: Record<string, Json>[]; windows: { oos: Record<string, Json> } } }).data
    data.milestones[0].status = 'nope'
    data.milestones[1].id = 0
    data.windows.oos.start = '2030-01-01'
    env = { ...(env as object) } as Json
    const errs = metaErrorsOf(metaData(env))
    expect(errs).toEqual([
      'data.ticker: expected a string, got number',
      'data.windows.oos: start 2030-01-01 must be before end_exclusive 2026-10-01',
      'data.milestones[0].status: expected one of done, current, planned, got "nope"',
      'data.milestones[1].id: duplicate id 0',
    ])
  })
})

describe('parseMeta: held_artifacts (the owner gate, added in 1.1.0)', () => {
  it('reads a file without the key, as every 1.0.x file is, as holding nothing', () => {
    const r = parseMeta(metaData(validMetaEnvelope()))
    expect(r.ok && r.meta.held_artifacts).toEqual([])
  })
  it('reads the held names when each is one of the artifacts', () => {
    let env = withValue(['data', 'artifacts'], ['meta', 'prices', 'eda'])
    ;(env as { data: Record<string, Json> }).data.held_artifacts = ['prices', 'eda']
    env = { ...(env as object) } as Json
    const r = parseMeta(metaData(env))
    expect(r.ok && r.meta.held_artifacts).toEqual(['prices', 'eda'])
  })
  it('refuses a held name that is not an artifact, and a value that is not an array', () => {
    expect(metaErrorsOf(metaData(withValue(['data', 'held_artifacts'], ['prices'])))).toEqual(['data.held_artifacts[0]: "prices" must be a listed artifact other than meta, named once'])
    expect(metaErrorsOf(metaData(withValue(['data', 'held_artifacts'], ['meta'])))).toEqual(['data.held_artifacts[0]: "meta" must be a listed artifact other than meta, named once'])
    expect(metaErrorsOf(metaData(withValue(['data', 'held_artifacts'], 'prices')))).toEqual(['data.held_artifacts: expected an array, got string'])
  })
})

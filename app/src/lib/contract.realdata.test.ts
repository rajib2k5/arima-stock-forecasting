/**
 * The cross-language drift check: the files that `tools/export_app_data.py` actually wrote into
 * `public/data/` must pass the production parsers. The other parser tests use a hand-built
 * fixture on purpose; this one reads whatever Python last exported, so a field renamed in Python
 * and re-exported fails here, not in a reader's browser.
 *
 * The owner gate (ADR-0001): `meta.data.held_artifacts` names files the export writes but the
 * repository does not commit (prices and eda), so a fresh clone lacks them. Each such file gets a
 * SKIPPED test whose name says why and how to build it. A listed file that is missing and not held
 * fails, so the gate can never hide a broken export.
 */
import { describe, expect, it } from 'vitest'
import { parseEnvelope, parseMeta } from './contract'
import { parseEda, parsePrices } from './contract.payloads'

// Every committed file, as raw text exactly as the browser receives it; JSON.parse below plays
// the part of `res.json()`, so a bare NaN token in a file fails here too.
const FILES = import.meta.glob<string>('../../public/data/*.json', { query: '?raw', import: 'default', eager: true })

type PayloadResult = { ok: true } | { ok: false; errors: string[] }

/** One payload parser per artifact. A new artifact must register its parser here, or this test fails. */
const PAYLOAD_PARSERS: Record<string, (data: unknown) => PayloadResult> = {
  meta: parseMeta,
  prices: parsePrices,
  eda: parseEda,
}

const stemOf = (path: string) => path.replace(/^.*\//, '').replace(/\.json$/, '')
const ENTRIES = Object.entries(FILES).map(([path, text]) => [stemOf(path), text] as const)

function readMeta() {
  const envelope = parseEnvelope(JSON.parse(FILES['../../public/data/meta.json']))
  return envelope.ok ? parseMeta(envelope.envelope.data) : envelope
}

const META = readMeta()
const LISTED = META.ok ? META.meta.artifacts : []
const HELD = META.ok ? META.meta.held_artifacts : []
const PRESENT = ENTRIES.map(([stem]) => stem)
const HELD_AND_ABSENT = HELD.filter((name) => !PRESENT.includes(name))

describe('the committed files in public/data', () => {
  it('include meta.json, which parses', () => {
    expect(PRESENT).toContain('meta')
    expect(META.ok ? [] : META.errors).toEqual([])
  })

  it.each(ENTRIES)('%s.json passes parseEnvelope, names itself, and passes its payload parser', (stem, text) => {
    const envelope = parseEnvelope(JSON.parse(text))
    expect(envelope.ok ? [] : envelope.errors).toEqual([])
    if (!envelope.ok) return
    expect(envelope.envelope.artifact).toBe(stem)
    const parse = PAYLOAD_PARSERS[stem]
    expect(parse, `no payload parser registered for the "${stem}" artifact`).toBeDefined()
    const payload = parse(envelope.envelope.data)
    expect(payload.ok ? [] : payload.errors).toEqual([])
  })

  it('are the artifacts that meta.json lists, less only those it marks as held', () => {
    expect([...PRESENT].sort()).toEqual(LISTED.filter((name) => PRESENT.includes(name) || !HELD.includes(name)).sort())
  })

  it.each(HELD)('every held artifact (%s) is one meta lists and has a registered parser', (name) => {
    expect(LISTED).toContain(name)
    expect(PAYLOAD_PARSERS[name]).toBeDefined()
  })

  // A skipped test per held file that this copy lacks, so the report says what was not checked.
  for (const name of HELD_AND_ABSENT) {
    it.skip(`${name}.json is not built in this copy: it is git-ignored until the owner decides whether Yahoo-derived prices may be published (ADR-0001); build it with uv run python tools/fetch_prices.py, then uv run python tools/export_app_data.py`, () => {})
  }
})

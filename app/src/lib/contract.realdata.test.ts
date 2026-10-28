/**
 * The cross-language drift check: the files that `tools/export_app_data.py` actually wrote into
 * `public/data/` must pass the production parsers. The other parser tests use a hand-built
 * fixture on purpose; this one reads whatever Python last exported, so a field renamed in Python
 * and re-exported fails here, not in a reader's browser.
 */
import { describe, expect, it } from 'vitest'
import { parseEnvelope, parseMeta } from './contract'

// Every committed file, as raw text exactly as the browser receives it; JSON.parse below plays
// the part of `res.json()`, so a bare NaN token in a file fails here too.
const FILES = import.meta.glob<string>('../../public/data/*.json', { query: '?raw', import: 'default', eager: true })

type PayloadResult = { ok: true } | { ok: false; errors: string[] }

/** One payload parser per artifact. A new artifact must register its parser here, or this test fails. */
const PAYLOAD_PARSERS: Record<string, (data: unknown) => PayloadResult> = {
  meta: parseMeta,
}

const stemOf = (path: string) => path.replace(/^.*\//, '').replace(/\.json$/, '')
const ENTRIES = Object.entries(FILES).map(([path, text]) => [stemOf(path), text] as const)

describe('the committed files in public/data', () => {
  it('include meta.json', () => {
    expect(ENTRIES.map(([stem]) => stem)).toContain('meta')
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

  it('are exactly the artifacts that meta.json lists', () => {
    const envelope = parseEnvelope(JSON.parse(FILES['../../public/data/meta.json']))
    const meta = envelope.ok ? parseMeta(envelope.envelope.data) : envelope
    expect(meta.ok ? [] : meta.errors).toEqual([])
    if (!meta.ok) return
    expect([...meta.meta.artifacts].sort()).toEqual(ENTRIES.map(([stem]) => stem).sort())
  })
})

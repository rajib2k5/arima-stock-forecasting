/**
 * parseMeta, parsePrices and parseEda against the shared corpus src/test/fixtures/payload_cases.json.
 * The Python suite runs the same cases through validate_meta, validate_prices and validate_eda
 * (tests/test_payload_corpus.py), so a rule changed on one side only fails a test on that side.
 */
import { describe, expect, it } from 'vitest'
import { parseMeta } from './contract'
import { parseEda, parsePrices } from './contract.payloads'
import corpus from '../test/fixtures/payload_cases.json'
import pricesBase from '../test/fixtures/prices.data.json'
import edaBase from '../test/fixtures/eda.data.json'
import metaBase from '../test/fixtures/meta.data.json'

type Json = null | boolean | number | string | Json[] | { [k: string]: Json }
interface Edit {
  path: (string | number)[]
  value?: Json
  delete?: boolean
}
interface Case {
  name: string
  base: 'meta' | 'prices' | 'eda'
  edits: Edit[]
  valid: boolean
}

const CASES = (corpus as unknown as { cases: Case[] }).cases
const BASES: Record<Case['base'], Json> = { meta: metaBase as Json, prices: pricesBase as Json, eda: edaBase as Json }
const PARSERS = { meta: parseMeta, prices: parsePrices, eda: parseEda }

/** A copy of the base payload with each edit applied: set the value at a path, or delete it. */
function apply(base: Json, edits: Edit[]): Json {
  const data = structuredClone(base)
  for (const edit of edits) {
    let node = data as Record<string | number, Json>
    for (const key of edit.path.slice(0, -1)) node = node[key] as Record<string | number, Json>
    const last = edit.path[edit.path.length - 1]
    if (edit.delete) {
      if (Array.isArray(node)) node.splice(last as number, 1)
      else delete node[last]
    } else node[last] = edit.value as Json
  }
  return data
}

describe('the shared payload corpus', () => {
  it('is a list of meta, prices and eda cases with both verdicts', () => {
    expect(CASES.length).toBeGreaterThanOrEqual(80)
    expect(new Set(CASES.map((c) => c.base))).toEqual(new Set(['meta', 'prices', 'eda']))
    expect(new Set(CASES.map((c) => c.valid))).toEqual(new Set([true, false]))
  })

  it.each(CASES.map((c) => [c.name, c] as const))('the TypeScript reader agrees: %s', (_name, c) => {
    const result = PARSERS[c.base](apply(BASES[c.base], c.edits))
    if (c.valid) expect(result.ok ? [] : result.errors).toEqual([])
    else expect(result.ok).toBe(false)
  })
})

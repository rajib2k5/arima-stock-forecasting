/**
 * Every payload parser against the shared corpus src/test/fixtures/payload_cases.json. The Python
 * suite runs the same cases through its validate_* functions (tests/test_payload_corpus.py), so a
 * rule changed on one side only fails a test on that side.
 */
import { describe, expect, it } from 'vitest'
import { parseMeta } from './contract'
import { parseEda, parsePrices } from './contract.payloads'
import { parseAcfPacf, parseAicGrid, parseStationarity } from './contract.order'
import { parseFit, parseResiduals } from './contract.fit'
import { loadArtifact } from '../data/loadArtifact'
import corpus from '../test/fixtures/payload_cases.json'
import pricesBase from '../test/fixtures/prices.data.json'
import edaBase from '../test/fixtures/eda.data.json'
import metaBase from '../test/fixtures/meta.data.json'
import stationarityBase from '../test/fixtures/stationarity.data.json'
import acfPacfBase from '../test/fixtures/acf_pacf.data.json'
import aicGridBase from '../test/fixtures/aic_grid.data.json'
import fitBase from '../test/fixtures/fit.data.json'
import residualsAicBase from '../test/fixtures/residuals_aic.data.json'

type Json = null | boolean | number | string | Json[] | { [k: string]: Json }
interface Edit {
  path: (string | number)[]
  value?: Json
  delete?: boolean
}
interface Case {
  name: string
  base: 'meta' | 'prices' | 'eda' | 'stationarity' | 'acf_pacf' | 'aic_grid' | 'fit' | 'residuals_aic'
  edits: Edit[]
  valid: boolean
}

interface TokenCase {
  name: string
  base: Case['base']
  path: (string | number)[]
  token: 'NaN' | 'Infinity' | '-Infinity'
}

const CASES = (corpus as unknown as { cases: Case[] }).cases
const TOKEN_CASES = (corpus as unknown as { token_cases: TokenCase[] }).token_cases
const BASES: Record<Case['base'], Json> = {
  meta: metaBase as Json,
  prices: pricesBase as Json,
  eda: edaBase as Json,
  stationarity: stationarityBase as unknown as Json,
  acf_pacf: acfPacfBase as unknown as Json,
  aic_grid: aicGridBase as unknown as Json,
  fit: fitBase as unknown as Json,
  residuals_aic: residualsAicBase as unknown as Json,
}
const PARSERS = {
  meta: parseMeta,
  prices: parsePrices,
  eda: parseEda,
  stationarity: parseStationarity,
  acf_pacf: parseAcfPacf,
  aic_grid: parseAicGrid,
  fit: parseFit,
  residuals_aic: (data: unknown) => parseResiduals(data, 'aic'),
}

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
  it('is a list of cases for every artifact, each with both verdicts', () => {
    expect(CASES.length).toBeGreaterThanOrEqual(200)
    expect(new Set(CASES.map((c) => c.base))).toEqual(new Set(Object.keys(PARSERS)))
    for (const base of Object.keys(PARSERS)) expect(new Set(CASES.filter((c) => c.base === base).map((c) => c.valid)), base).toEqual(new Set([true, false]))
  })

  it.each(CASES.map((c) => [c.name, c] as const))('the TypeScript reader agrees: %s', (_name, c) => {
    const result = PARSERS[c.base](apply(BASES[c.base], c.edits))
    if (c.valid) {
      expect(result.ok ? [] : result.errors).toEqual([])
      expect(result.ok).toBe(true) // a refusal with an empty error list must not pass for a yes
    } else {
      expect(result.ok).toBe(false)
      expect(result.ok ? [] : result.errors).not.toEqual([]) // and a refusal says why
    }
  })
})

/** The whole envelope as text, with one bare NaN or Infinity token at the case's path (as tests/test_payload_corpus.py builds it). */
function tokenText(c: TokenCase): string {
  const data = structuredClone(BASES[c.base]) as Record<string | number, Json>
  let node = data
  for (const key of c.path.slice(0, -1)) node = node[key] as Record<string | number, Json>
  node[c.path[c.path.length - 1]] = '__TOKEN__'
  const envelope = { schema_version: '1.4.0', artifact: c.base, generated_at: '2026-10-29T00:00:00Z', source_commit: '0'.repeat(40), data }
  return JSON.stringify(envelope).replace('"__TOKEN__"', c.token)
}

describe('NaN and Infinity written as JSON tokens', () => {
  it('are six or more cases, each with a bare token in its text', () => {
    expect(TOKEN_CASES.length).toBeGreaterThanOrEqual(6)
    expect(new Set(TOKEN_CASES.map((c) => c.token))).toEqual(new Set(['NaN', 'Infinity', '-Infinity']))
    for (const c of TOKEN_CASES) expect(tokenText(c)).toContain(`:${c.token}`)
  })

  it.each(TOKEN_CASES.map((c) => [c.name, c] as const))('the app refuses the file when it parses it: %s', async (_name, c) => {
    const text = tokenText(c)
    const fetchImpl = async () => new Response(text, { status: 200, headers: { 'content-type': 'application/json' } })
    const result = await loadArtifact(c.base, fetchImpl)
    expect(result.ok).toBe(false)
    expect(result.ok ? undefined : result.error.kind).toBe('json')
  })
})

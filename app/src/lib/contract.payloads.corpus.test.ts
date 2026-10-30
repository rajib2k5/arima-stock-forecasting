/**
 * Every payload parser against the shared corpus src/test/fixtures/payload_cases.json. The Python
 * suite runs the same cases through its validate_* functions (tests/test_payload_corpus.py), so a
 * rule changed on one side only fails a test on that side.
 */
import { describe, expect, it } from 'vitest'
import { MAX_PROBLEMS, moreProblems, parseMeta } from './contract'
import { parseEda, parsePrices } from './contract.payloads'
import { parseAcfPacf, parseAicGrid, parseStationarity } from './contract.order'
import { parseFit, parseResiduals } from './contract.fit'
import { parseEvaluation, parseForecast } from './contract.forecast'
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
import forecastAicStaticBase from '../test/fixtures/forecast_aic_static.data.json'
import forecastAicWalkForwardBase from '../test/fixtures/forecast_aic_walk_forward.data.json'
import forecastAicRefitBase from '../test/fixtures/forecast_aic_refit.data.json'
import evaluationBase from '../test/fixtures/evaluation.data.json'

type Json = null | boolean | number | string | Json[] | { [k: string]: Json }
interface Edit {
  path: (string | number)[]
  value?: Json
  delete?: boolean
}
interface Case {
  name: string
  base: 'meta' | 'prices' | 'eda' | 'stationarity' | 'acf_pacf' | 'aic_grid' | 'fit' | 'residuals_aic' | 'forecast_aic_static' | 'forecast_aic_walk_forward' | 'forecast_aic_refit' | 'evaluation'
  edits: Edit[]
  valid: boolean
  /**
   * For an invalid case, the path prefixes its problems are reported under: every problem must start with
   * one of them, so a case refused for some other rule as well fails (milestone-4 bases and the warnings bound).
   */
  paths?: string[]
}

/** `count` copies of one item in the list at `path`: the list's first entry, the number 0, or `value` (after `edits`). */
interface SizeCase {
  name: string
  base: Case['base']
  path: (string | number)[]
  count: number
  item?: 'first' | 'zero'
  value?: Json
  edits?: Edit[]
  /** One past the bound: exactly these errors, in the words Python uses too. */
  problems?: string[]
  /** At the bound: no error starts with this (the list is read, not refused for its length). */
  absent?: string
  seconds?: number
  /** A list inside each copy too (cap_cases): `count` copies of `value` at `path` of the item. */
  inner?: { path: (string | number)[]; count: number; value: Json }
}

interface TokenCase {
  name: string
  base: Case['base']
  path: (string | number)[]
  token: 'NaN' | 'Infinity' | '-Infinity'
}

const CASES = (corpus as unknown as { cases: Case[] }).cases
const TOKEN_CASES = (corpus as unknown as { token_cases: TokenCase[] }).token_cases
const SIZE_CASES = (corpus as unknown as { size_cases: SizeCase[] }).size_cases
const BASES: Record<Case['base'], Json> = {
  meta: metaBase as Json,
  prices: pricesBase as Json,
  eda: edaBase as Json,
  stationarity: stationarityBase as unknown as Json,
  acf_pacf: acfPacfBase as unknown as Json,
  aic_grid: aicGridBase as unknown as Json,
  fit: fitBase as unknown as Json,
  residuals_aic: residualsAicBase as unknown as Json,
  forecast_aic_static: forecastAicStaticBase as unknown as Json,
  forecast_aic_walk_forward: forecastAicWalkForwardBase as unknown as Json,
  forecast_aic_refit: forecastAicRefitBase as unknown as Json,
  evaluation: evaluationBase as unknown as Json,
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
  // The file name gives the model and method, as contract.realdata.test.ts passes them.
  forecast_aic_static: (data: unknown) => parseForecast(data, 'aic', 'static'),
  forecast_aic_walk_forward: (data: unknown) => parseForecast(data, 'aic', 'walk_forward'),
  forecast_aic_refit: (data: unknown) => parseForecast(data, 'aic', 'refit'),
  evaluation: parseEvaluation,
}

/** The path an error is reported at: the text before its first ": " ("data.dm[2].var_diff: must be ..."). */
const pathOf = (error: string) => error.split(': ')[0]

/** `path` is `prefix` or lies under it ("data.dm[2]" holds "data.dm[2].var_diff" and "data.dm[2]", not "data.dm[20]"). */
const under = (path: string, prefix: string) => path === prefix || path.startsWith(`${prefix}.`) || path.startsWith(`${prefix}[`)

/** The bases of milestone 4, whose every invalid case names its paths. */
const PATHED: readonly string[] = ['forecast_aic_static', 'forecast_aic_walk_forward', 'forecast_aic_refit', 'evaluation']

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

  it('names, for every invalid milestone-4 case, the paths its problems must be reported under', () => {
    const missing = CASES.filter((c) => PATHED.includes(c.base) && !c.valid && !(c.paths && c.paths.length > 0)).map((c) => c.name)
    expect(missing).toEqual([])
    expect(CASES.filter((c) => c.valid && c.paths !== undefined).map((c) => c.name)).toEqual([])
  })

  it.each(CASES.map((c) => [c.name, c] as const))('the TypeScript reader agrees: %s', (_name, c) => {
    const result = PARSERS[c.base](apply(BASES[c.base], c.edits))
    if (c.valid) {
      expect(result.ok ? [] : result.errors).toEqual([])
      expect(result.ok).toBe(true) // a refusal with an empty error list must not pass for a yes
    } else {
      expect(result.ok).toBe(false)
      expect(result.ok ? [] : result.errors).not.toEqual([]) // and a refusal says why
      // Refused for its own rule only: no problem outside the case's paths.
      if (c.paths) expect((result.ok ? [] : result.errors).filter((e) => !c.paths!.some((p) => under(pathOf(e), p)))).toEqual([])
    }
  })
})

/** The case's base with `count` copies of its item in the list at its path (as tests/test_payload_corpus.py builds it). */
function sized(c: SizeCase): Json {
  const data = apply(BASES[c.base], c.edits ?? []) as Record<string | number, Json>
  let node = data
  for (const key of c.path.slice(0, -1)) node = node[key] as Record<string | number, Json>
  const last = c.path[c.path.length - 1]
  let item = c.item === 'first' ? (node[last] as Json[])[0] : c.item === 'zero' ? 0 : (c.value as Json)
  if (c.inner) {
    // A list inside each copy too: `inner.count` copies of `inner.value` at `inner.path` of the item.
    item = structuredClone(item)
    let holder = item as Record<string | number, Json>
    for (const key of c.inner.path.slice(0, -1)) holder = holder[key] as Record<string | number, Json>
    holder[c.inner.path[c.inner.path.length - 1]] = new Array<Json>(c.inner.count).fill(c.inner.value)
  }
  node[last] = new Array<Json>(c.count).fill(item)
  return data
}

describe('every list bounded before it is walked', () => {
  it('has a case one past and a case at the bound of each list', () => {
    expect(SIZE_CASES.length).toBeGreaterThanOrEqual(70)
    const key = (c: SizeCase) => `${c.base} ${JSON.stringify(c.path)}`
    const over = new Set(SIZE_CASES.filter((c) => c.problems && c.count < 1_000_000).map(key))
    expect(new Set(SIZE_CASES.filter((c) => c.absent !== undefined).map(key))).toEqual(over)
  })

  it.each(SIZE_CASES.map((c) => [c.name, c] as const))('the TypeScript reader agrees: %s', (_name, c) => {
    const data = sized(c)
    const start = performance.now()
    const result = PARSERS[c.base](data)
    const seconds = (performance.now() - start) / 1000
    const errors = result.ok ? [] : result.errors
    if (c.problems) expect(errors).toEqual(c.problems)
    else expect(errors.filter((e) => e.startsWith(c.absent!)).slice(0, 3)).toEqual([])
    expect(seconds).toBeLessThan(c.seconds ?? 5)
  })
})

const CAP_CASES = (corpus as unknown as { cap_cases: (SizeCase & { problems: string[] })[] }).cap_cases

describe('one bound on the problems of a file', () => {
  it('stops each cap case at MAX_PROBLEMS with the one line that says so', () => {
    expect(CAP_CASES.length).toBeGreaterThanOrEqual(5)
    expect(CAP_CASES.some((c) => c.inner !== undefined)).toBe(true)
    for (const c of CAP_CASES) expect([c.problems.length, c.problems[c.problems.length - 1]], c.name).toEqual([MAX_PROBLEMS + 1, moreProblems('data')])
  })

  // Word for word what Python gives (tests/test_payload_corpus.py): the same first 200 problems in the same order, then the same last line.
  it.each(CAP_CASES.map((c) => [c.name, c] as const))('the TypeScript reader stops where Python does: %s', (_name, c) => {
    const data = sized(c)
    const start = performance.now()
    const result = PARSERS[c.base](data)
    expect((performance.now() - start) / 1000).toBeLessThan(c.seconds ?? 1)
    expect(result.ok ? [] : result.errors).toEqual(c.problems)
  })
})

/** The whole envelope as text, with one bare NaN or Infinity token at the case's path (as tests/test_payload_corpus.py builds it). */
function tokenText(c: TokenCase): string {
  const data = structuredClone(BASES[c.base]) as Record<string | number, Json>
  let node = data
  for (const key of c.path.slice(0, -1)) node = node[key] as Record<string | number, Json>
  node[c.path[c.path.length - 1]] = '__TOKEN__'
  const envelope = { schema_version: '1.5.0', artifact: c.base, generated_at: '2026-10-29T00:00:00Z', source_commit: '0'.repeat(40), data }
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

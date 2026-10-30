/**
 * Hostile files against the TypeScript readers: a value of any size or depth, a file of any number of
 * problems. Each must give short errors, quickly, and never throw (contract.md, "Bounds"). Python's
 * tests/test_payloads_hostile.py makes the same attacks on payloads.py, and the shared corpus's cap_cases
 * hold both readers to the same capped result. Every value is made up: the bases are the fixtures.
 */
import { describe, expect, it } from 'vitest'
import { MAX_PROBLEMS, moreProblems, parseEnvelope, parseMeta, shown } from './contract'
import { parseEda, parsePrices } from './contract.payloads'
import { parseAcfPacf, parseAicGrid, parseStationarity } from './contract.order'
import { parseFit, parseResiduals } from './contract.fit'
import { parseEvaluation, parseForecast } from './contract.forecast'
import pricesBase from '../test/fixtures/prices.data.json'
import edaBase from '../test/fixtures/eda.data.json'
import metaBase from '../test/fixtures/meta.data.json'
import stationarityBase from '../test/fixtures/stationarity.data.json'
import acfPacfBase from '../test/fixtures/acf_pacf.data.json'
import aicGridBase from '../test/fixtures/aic_grid.data.json'
import fitBase from '../test/fixtures/fit.data.json'
import residualsAicBase from '../test/fixtures/residuals_aic.data.json'
import forecastAicStaticBase from '../test/fixtures/forecast_aic_static.data.json'
import forecastAicRefitBase from '../test/fixtures/forecast_aic_refit.data.json'
import evaluationBase from '../test/fixtures/evaluation.data.json'

type Json = null | boolean | number | string | Json[] | { [k: string]: Json }
type Result = { ok: true } | { ok: false; errors: string[] }

const PARSERS: Record<string, [Json, (data: unknown) => Result]> = {
  meta: [metaBase as Json, parseMeta],
  prices: [pricesBase as Json, parsePrices],
  eda: [edaBase as Json, parseEda],
  stationarity: [stationarityBase as unknown as Json, parseStationarity],
  acf_pacf: [acfPacfBase as unknown as Json, parseAcfPacf],
  aic_grid: [aicGridBase as unknown as Json, parseAicGrid],
  fit: [fitBase as unknown as Json, parseFit],
  residuals_aic: [residualsAicBase as unknown as Json, (data) => parseResiduals(data, 'aic')],
  forecast_aic_static: [forecastAicStaticBase as unknown as Json, (data) => parseForecast(data, 'aic', 'static')],
  forecast_aic_refit: [forecastAicRefitBase as unknown as Json, (data) => parseForecast(data, 'aic', 'refit')],
  evaluation: [evaluationBase as unknown as Json, parseEvaluation],
}
/** No error may be longer than this many characters, whatever the value it quotes (tests/test_payloads_hostile.py's SHORT). */
const SHORT = 400

const errorsOf = (r: Result) => (r.ok ? [] : r.errors)

function put(base: Json, path: (string | number)[], value: unknown): Json {
  const data = structuredClone(base)
  let node = data as Record<string | number, Json>
  for (const key of path.slice(0, -1)) node = node[key] as Record<string | number, Json>
  node[path[path.length - 1]] = value as Json
  return data
}

/** Every path down to `most` levels (the first three items of each list). */
function nodes(node: Json, prefix: (string | number)[] = [], depth = 0, most = 6): (string | number)[][] {
  if (depth > most || node === null || typeof node !== 'object') return []
  const items: [string | number, Json][] = Array.isArray(node) ? node.slice(0, 3).map((v, i) => [i, v]) : Object.entries(node)
  return items.flatMap(([key, child]) => [[...prefix, key], ...nodes(child, [...prefix, key], depth + 1, most)])
}

function expectShort(errors: string[], what: string): void {
  expect(errors.length, what).toBeGreaterThan(0)
  expect(errors.length, what).toBeLessThanOrEqual(MAX_PROBLEMS + 1)
  expect(errors.filter((e) => e.length > SHORT).map((e) => e.slice(0, 120)), what).toEqual([])
}

/** A 100,000-deep array: V8's JSON.parse reads it, and JSON.stringify of it throws RangeError. */
const DEEP: unknown = JSON.parse('['.repeat(100_000) + ']'.repeat(100_000))
const BIG = '2'.repeat(60_000_000)

describe('the one quoting function', () => {
  it('quotes a value of any size or depth in a few words, and never walks into it', () => {
    expect(shown(BIG)).toBe(`"${'2'.repeat(80)}"… (60000000 characters)`)
    expect(shown(DEEP)).toBe('an array of 1')
    expect(() => JSON.stringify(DEEP)).toThrow(RangeError) // what a message used to call on such a value
  })
})

describe('a value of 60 MB', () => {
  const spots: [string, (string | number)[]][] = [
    ['prices', ['rows', 0, 'date']],
    ['prices', ['rows', 0, 'segment']],
    ['prices', ['source', 'raw_sha256']],
    ['prices', ['source', 'downloaded_at']],
    ['prices', ['splits', 'oos', 'start']],
    ['meta', ['milestones', 0, 'status']],
    ['meta', ['milestones', 0, 'id']],
    ['meta', ['windows', 'oos', 'end_exclusive']],
    ['eda', ['summary', 'start']],
    ['aic_grid', ['cells', 0, 'start']],
    ['fit', ['models', 0, 'params', 0, 'name']],
    ['forecast_aic_static', ['label']],
    ['forecast_aic_refit', ['refits', 0, 'params', 0, 'name']],
    ['evaluation', ['models', 0, 'label']],
    ['evaluation', ['methods', 0, 'label']],
  ]
  it.each(spots)('gives a short error at %s %j', (name, path) => {
    const [base, parse] = PARSERS[name]
    const t0 = performance.now()
    const errors = errorsOf(parse(put(base, path, BIG)))
    expect(performance.now() - t0).toBeLessThan(1000)
    expectShort(errors, `${name} ${path.join('.')}`)
    expect(errors.some((e) => e.includes('(60000000 characters)')), errors.join('; ').slice(0, 300)).toBe(true)
  })

  it('gives a short error for two KDEs of one 60 MB variable, a 60 MB params key, and a 60 MB held artifact', () => {
    const kdes = structuredClone((edaBase as { kdes: Json[] }).kdes) as { variable: string }[]
    kdes[0].variable = kdes[1].variable = BIG
    expectShort(errorsOf(parseEda(put(edaBase as Json, ['kdes'], kdes))), 'a duplicate 60 MB variable')
    expectShort(errorsOf(parseAicGrid(put(aicGridBase as unknown as Json, ['cells', 0, 'params'], { [BIG]: 'x' }))), 'a 60 MB params key')
    expectShort(errorsOf(parseMeta(put(metaBase as Json, ['held_artifacts'], [BIG]))), 'a 60 MB held artifact')
    expect(errorsOf(parseMeta(put(metaBase as Json, ['held_artifacts'], [BIG]))).some((e) => e.includes('(60000000 characters)'))).toBe(true)
  })

  it.each(['schema_version', 'artifact', 'generated_at', 'source_commit'])('gives a short error for a 60 MB envelope %s, and for a 60 MB unknown key', (key) => {
    const envelope = { schema_version: '1.5.0', artifact: 'meta', generated_at: '2026-10-29T00:00:00Z', source_commit: 'uncommitted', data: {} }
    expectShort(errorsOf(parseEnvelope({ ...envelope, [key]: BIG })), key)
    expectShort(errorsOf(parseEnvelope({ ...envelope, [BIG]: 1 })), 'a 60 MB key')
    expectShort(errorsOf(parseEnvelope({ ...envelope, schema_version: `1${'0'.repeat(5000)}.0.0` })), 'a 5,001-digit major')
  })
})

describe('one bound on the problems of a file', () => {
  it('stops an envelope with a million unknown keys at MAX_PROBLEMS, with the line that says so', () => {
    const envelope: Record<string, unknown> = { schema_version: '1.5.0', artifact: 'meta', generated_at: '2026-10-29T00:00:00Z', source_commit: 'uncommitted', data: {} }
    for (let i = 0; i < 1_000_000; i++) envelope[`k${String(i).padStart(7, '0')}`] = 0
    const t0 = performance.now()
    const errors = errorsOf(parseEnvelope(envelope))
    expect(performance.now() - t0).toBeLessThan(2000)
    expect(errors).toEqual([...Array.from({ length: MAX_PROBLEMS }, (_, i) => `"k${String(i).padStart(7, '0')}": unexpected key`), moreProblems('envelope')])
  })

  it('never lets a parser pass MAX_PROBLEMS: every list of every fixture filled with empty objects', () => {
    for (const [name, [base, parse]] of Object.entries(PARSERS)) {
      const data = structuredClone(base)
      for (const path of nodes(data)) {
        let node = data as Record<string | number, Json>
        for (const key of path.slice(0, -1)) node = (node?.[key] ?? null) as Record<string | number, Json>
        const v = node?.[path[path.length - 1]]
        if (Array.isArray(v) && v.length > 1) node[path[path.length - 1]] = v.map(() => ({}))
      }
      const errors = errorsOf(parse(data))
      expect(errors.length, name).toBeLessThanOrEqual(MAX_PROBLEMS + 1)
      if (errors.length > MAX_PROBLEMS) expect(errors[errors.length - 1], name).toBe(moreProblems('data'))
    }
  })
})

describe('a 100,000-deep array', () => {
  it.each([
    ['prices', ['rows', 0, 'segment']],
    ['meta', ['milestones', 0, 'id']],
    ['meta', ['artifacts', 0]],
    ['meta', ['held_artifacts', 0]],
  ] as [string, (string | number)[]][])('gives one short error at %s %j (each threw RangeError before)', (name, path) => {
    const [base, parse] = PARSERS[name]
    const errors = errorsOf(parse(put(base, path, DEEP)))
    expectShort(errors, path.join('.'))
    expect(errors.some((e) => e.includes('an array of 1'))).toBe(true)
  })

  it.each(Object.keys(PARSERS))('in place of any node of %s gives short errors, never a RangeError', (name) => {
    const [base, parse] = PARSERS[name]
    const paths = nodes(base)
    expect(paths.length).toBeGreaterThan(20)
    for (const path of paths) {
      const errors = errorsOf(parse(put(base, path, DEEP))) // must not throw
      expect(errors.length, path.join('.')).toBeLessThanOrEqual(MAX_PROBLEMS + 1)
      expect(errors.filter((e) => e.length > SHORT), path.join('.')).toEqual([])
    }
  })

  it('in the envelope gives one short error', () => {
    const envelope = { schema_version: '1.5.0', artifact: 'meta', generated_at: '2026-10-29T00:00:00Z', source_commit: 'uncommitted', data: {} }
    for (const key of ['schema_version', 'artifact', 'generated_at', 'source_commit', 'data', 'extra']) expectShort(errorsOf(parseEnvelope({ ...envelope, [key]: DEEP })), key)
  })
})

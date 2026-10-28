import { describe, expect, it, vi } from 'vitest'
import { loadArtifact, type FetchLike } from './loadArtifact'
import { validMetaEnvelope, withValue } from '../test/fixtures/fixtures'

const respond = (over: Partial<Awaited<ReturnType<FetchLike>>> & { body?: unknown; jsonError?: Error }): FetchLike =>
  vi.fn(async () => ({
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => {
      if (over.jsonError) throw over.jsonError
      return over.body
    },
    ...over,
  }))

describe('loadArtifact', () => {
  it('fetches data/<name>.json next to the page and returns the parsed envelope on 200', async () => {
    const fetchImpl = respond({ body: validMetaEnvelope() })
    const res = await loadArtifact('meta', fetchImpl)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
    const url = vi.mocked(fetchImpl).mock.calls[0][0]
    expect(url).toBe(`${import.meta.env.BASE_URL}data/meta.json`)
    expect(url.endsWith('data/meta.json')).toBe(true)
    expect(res.ok).toBe(true)
    if (res.ok) {
      expect(res.envelope.artifact).toBe('meta')
      expect(res.envelope.schema_version).toBe('1.0.0')
      expect(res.envelope.data).toMatchObject({ ticker: 'AAPL' })
    }
  })

  it('turns a 404 into a typed http error carrying the status', async () => {
    const res = await loadArtifact('meta', respond({ ok: false, status: 404, statusText: 'Not Found' }))
    expect(res).toEqual({
      ok: false,
      error: { kind: 'http', url: `${import.meta.env.BASE_URL}data/meta.json`, status: 404, statusText: 'Not Found' },
    })
  })

  it('turns a 500 into a typed http error too (any non-OK status)', async () => {
    const res = await loadArtifact('meta', respond({ ok: false, status: 500, statusText: '' }))
    expect(res.ok).toBe(false)
    if (!res.ok) expect(res.error).toMatchObject({ kind: 'http', status: 500 })
  })

  it('turns invalid JSON (for example an HTML fallback page served with 200) into a typed json error', async () => {
    const res = await loadArtifact('meta', respond({ jsonError: new SyntaxError("Unexpected token '<'") }))
    expect(res.ok).toBe(false)
    if (!res.ok) {
      expect(res.error.kind).toBe('json')
      if (res.error.kind === 'json') expect(res.error.message).toContain("Unexpected token '<'")
    }
  })

  it('turns a rejected fetch (offline, DNS, CORS) into a typed network error', async () => {
    const fetchImpl: FetchLike = async () => {
      throw new TypeError('Failed to fetch')
    }
    const res = await loadArtifact('meta', fetchImpl)
    expect(res).toEqual({ ok: false, error: { kind: 'network', url: `${import.meta.env.BASE_URL}data/meta.json`, message: 'Failed to fetch' } })
  })

  it('returns the contract errors when the JSON is not a valid envelope', async () => {
    const res = await loadArtifact('meta', respond({ body: withValue(['schema_version'], '2.0.0') }))
    expect(res).toEqual({
      ok: false,
      error: { kind: 'contract', errors: ['schema_version: major version 2 is not supported (this app reads 1.x.y)'] },
    })
  })

  it('rejects an envelope whose artifact name is not the one requested', async () => {
    const res = await loadArtifact('prices', respond({ body: validMetaEnvelope() }))
    expect(res).toEqual({ ok: false, error: { kind: 'artifact_mismatch', expected: 'prices', actual: 'meta' } })
  })

  it.each(['../secret', 'meta/../x', 'Meta', '', 'a b', 'meta.json', '1meta', 'meta?x=1'])('refuses the artifact name %j without fetching', async (name) => {
    const fetchImpl = respond({ body: validMetaEnvelope() })
    const res = await loadArtifact(name, fetchImpl)
    expect(res).toEqual({ ok: false, error: { kind: 'invalid_name', name } })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('uses the global fetch when none is injected', async () => {
    const real = globalThis.fetch
    const spy = vi.fn(async () => ({ ok: true, status: 200, statusText: 'OK', json: async () => validMetaEnvelope() }) as unknown as Response)
    globalThis.fetch = spy as typeof fetch
    try {
      const res = await loadArtifact('meta')
      expect(spy).toHaveBeenCalledTimes(1)
      expect(res.ok).toBe(true)
    } finally {
      globalThis.fetch = real
    }
  })
})

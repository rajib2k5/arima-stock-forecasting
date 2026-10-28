import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { loadMeta, useMeta } from './useMeta'
import type { LoadResult } from './loadArtifact'
import { VALID_COMMIT, validMetaEnvelope, withValue } from '../test/fixtures/fixtures'

const okResult = (env = validMetaEnvelope()): LoadResult => {
  const e = env as { schema_version: string; artifact: string; generated_at: string; source_commit: string; data: Record<string, unknown> }
  return { ok: true, envelope: e }
}

describe('loadMeta', () => {
  it('asks for the meta artifact and returns envelope plus typed meta when both layers validate', async () => {
    let asked = ''
    const state = await loadMeta(async (name) => {
      asked = name
      return okResult()
    })
    expect(asked).toBe('meta')
    expect(state.status).toBe('ready')
    if (state.status === 'ready') {
      expect(state.meta.ticker).toBe('AAPL')
      expect(state.envelope.source_commit).toBe(VALID_COMMIT)
    }
  })
  it('passes a loader failure through unchanged', async () => {
    const error = { kind: 'http', url: 'x', status: 404, statusText: 'Not Found' } as const
    expect(await loadMeta(async () => ({ ok: false, error }))).toEqual({ status: 'error', error })
  })
  it('reports payload problems as contract errors even when the envelope itself is fine', async () => {
    const state = await loadMeta(async () => okResult(withValue(['data', 'ticker'], 7)))
    expect(state).toEqual({ status: 'error', error: { kind: 'contract', errors: ['data.ticker: expected a string, got number'] } })
  })
})

describe('useMeta', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts loading, then becomes ready when the data file is valid', async () => {
    vi.stubGlobal('fetch', async () => ({ ok: true, status: 200, statusText: 'OK', json: async () => validMetaEnvelope() }))
    const { result } = renderHook(() => useMeta())
    expect(result.current).toEqual({ status: 'loading' })
    await waitFor(() => expect(result.current.status).toBe('ready'))
    if (result.current.status === 'ready') expect(result.current.meta.windows.oos.end_exclusive).toBe('2026-10-01')
  })

  it('becomes an error when the fetch fails', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('Failed to fetch')
    })
    const { result } = renderHook(() => useMeta())
    await waitFor(() => expect(result.current.status).toBe('error'))
    if (result.current.status === 'error') expect(result.current.error.kind).toBe('network')
  })
})

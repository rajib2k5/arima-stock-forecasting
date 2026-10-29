import { describe, expect, it } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { loadExplorer, useExplorerData } from './useExplorerData'
import type { LoadResult } from './loadArtifact'
import { edaEnvelope, pricesEnvelope } from '../test/fixtures/payloads'
import type { Envelope } from '../lib/contract'

const ok = (env: unknown): LoadResult => ({ ok: true, envelope: env as Envelope })
const fakeLoad = (envs: Record<string, LoadResult>) => async (name: string) => envs[name]

describe('loadExplorer', () => {
  it('loads prices and eda and returns both parsed payloads', async () => {
    const asked: string[] = []
    const state = await loadExplorer(async (name) => {
      asked.push(name)
      return ok(name === 'prices' ? pricesEnvelope() : edaEnvelope())
    })
    expect(asked.sort()).toEqual(['eda', 'prices'])
    expect(state.status).toBe('ready')
    if (state.status !== 'ready') return
    expect(state.prices.rows).toHaveLength(6)
    expect(state.eda.summary.n).toBe(4)
    expect(state.envelopes.prices.schema_version).toBe('1.1.0')
  })

  it('names the artifact whose load failed', async () => {
    const error = { kind: 'http', url: './data/eda.json', status: 404, statusText: 'Not Found' } as const
    expect(await loadExplorer(fakeLoad({ prices: ok(pricesEnvelope()), eda: { ok: false, error } }))).toEqual({ status: 'error', artifact: 'eda', error })
    expect(await loadExplorer(fakeLoad({ prices: { ok: false, error }, eda: ok(edaEnvelope()) }))).toEqual({ status: 'error', artifact: 'prices', error })
  })

  it('turns a payload that breaks the contract into a contract error for that artifact', async () => {
    const badPrices = pricesEnvelope() as { data: { price_basis: string } }
    badPrices.data.price_basis = 'close'
    expect(await loadExplorer(fakeLoad({ prices: ok(badPrices), eda: ok(edaEnvelope()) }))).toEqual({
      status: 'error',
      artifact: 'prices',
      error: { kind: 'contract', errors: ['data.price_basis: expected "adjusted_close", got "close"'] },
    })
    const badEda = edaEnvelope() as { data: { sample: string } }
    badEda.data.sample = 'test'
    expect(await loadExplorer(fakeLoad({ prices: ok(pricesEnvelope()), eda: ok(badEda) }))).toEqual({
      status: 'error',
      artifact: 'eda',
      error: { kind: 'contract', errors: ['data.sample: expected "train", got "test"'] },
    })
  })
})

describe('useExplorerData', () => {
  it('starts loading, then becomes ready', async () => {
    const load = fakeLoad({ prices: ok(pricesEnvelope()), eda: ok(edaEnvelope()) })
    const { result } = renderHook(() => useExplorerData(load))
    expect(result.current).toEqual({ status: 'loading' })
    await waitFor(() => expect(result.current.status).toBe('ready'))
  })
})

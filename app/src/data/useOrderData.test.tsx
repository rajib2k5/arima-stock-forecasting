import { describe, expect, it } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { parseEnvelope } from '../lib/contract'
import { loadLandscape, loadStationarity, useLandscapeData, useStationarityData } from './useOrderData'
import type { LoadResult } from './loadArtifact'
import { orderEnvelope } from '../test/fixtures/payloads'

function fakeLoad(overrides: Record<string, LoadResult> = {}) {
  return async (name: string): Promise<LoadResult> => {
    if (overrides[name]) return overrides[name]
    const parsed = parseEnvelope(orderEnvelope(name as 'stationarity' | 'acf_pacf' | 'aic_grid'))
    if (!parsed.ok) throw new Error(parsed.errors.join('; '))
    return { ok: true, envelope: parsed.envelope }
  }
}

const NOT_FOUND: LoadResult = { ok: false, error: { kind: 'http', url: './data/x.json', status: 404, statusText: 'Not Found' } }

describe('loadStationarity', () => {
  it('parses both files', async () => {
    const state = await loadStationarity(fakeLoad())
    expect(state.status).toBe('ready')
    if (state.status !== 'ready') return
    expect(state.stationarity.decision.d_selected).toBe(1)
    expect(state.acfPacf.nlags).toBe(3)
    expect(state.envelopes.acf_pacf.artifact).toBe('acf_pacf')
  })

  it('names the file that failed to load, stationarity first', async () => {
    expect(await loadStationarity(fakeLoad({ acf_pacf: NOT_FOUND }))).toMatchObject({ status: 'error', artifact: 'acf_pacf', error: { kind: 'http' } })
    expect(await loadStationarity(fakeLoad({ stationarity: NOT_FOUND, acf_pacf: NOT_FOUND }))).toMatchObject({ status: 'error', artifact: 'stationarity' })
  })

  it('turns a payload the parser refuses into a contract error with every problem', async () => {
    const bad = parseEnvelope({ ...(orderEnvelope('stationarity') as object), data: { sample: 'oos' } })
    if (!bad.ok) throw new Error('fixture')
    const state = await loadStationarity(fakeLoad({ stationarity: { ok: true, envelope: bad.envelope } }))
    expect(state).toMatchObject({ status: 'error', artifact: 'stationarity', error: { kind: 'contract' } })
    if (state.status === 'error' && state.error.kind === 'contract') expect(state.error.errors).toContain('data.sample: expected "train", got "oos"')
  })

  it('refuses a broken acf_pacf payload too', async () => {
    const bad = parseEnvelope({ ...(orderEnvelope('acf_pacf') as object), data: {} })
    if (!bad.ok) throw new Error('fixture')
    expect(await loadStationarity(fakeLoad({ acf_pacf: { ok: true, envelope: bad.envelope } }))).toMatchObject({ status: 'error', artifact: 'acf_pacf', error: { kind: 'contract' } })
  })
})

describe('loadLandscape', () => {
  it('parses the grid, or names it when it fails', async () => {
    const state = await loadLandscape(fakeLoad())
    expect(state.status === 'ready' && state.aicGrid.selection.order).toEqual([0, 1, 1])
    expect(await loadLandscape(fakeLoad({ aic_grid: NOT_FOUND }))).toMatchObject({ status: 'error', artifact: 'aic_grid' })
    const bad = parseEnvelope({ ...(orderEnvelope('aic_grid') as object), data: { sample: 'train' } })
    if (!bad.ok) throw new Error('fixture')
    expect(await loadLandscape(fakeLoad({ aic_grid: { ok: true, envelope: bad.envelope } }))).toMatchObject({ status: 'error', error: { kind: 'contract' } })
  })
})

describe('the hooks', () => {
  it('start loading and then hold the parsed data', async () => {
    const load = fakeLoad()
    const st = renderHook(() => useStationarityData(load))
    expect(st.result.current.status).toBe('loading')
    await waitFor(() => expect(st.result.current.status).toBe('ready'))
    const ls = renderHook(() => useLandscapeData(load))
    await waitFor(() => expect(ls.result.current.status).toBe('ready'))
  })
})

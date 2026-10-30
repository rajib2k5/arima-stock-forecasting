import { describe, expect, it } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { parseEnvelope } from '../lib/contract'
import type { ModelId } from '../lib/contract.fit'
import { loadFit, loadResiduals, useFitData, useResidualsData } from './useFitData'
import type { LoadResult } from './loadArtifact'
import { fitEnvelope } from '../test/fixtures/payloads'

/** A fake loader over the made-up envelopes that records every artifact asked for. */
function fakeLoad(overrides: Record<string, LoadResult> = {}) {
  const calls: string[] = []
  const load = async (name: string): Promise<LoadResult> => {
    calls.push(name)
    if (overrides[name]) return overrides[name]
    const parsed = parseEnvelope(fitEnvelope(name as 'fit' | `residuals_${ModelId}`))
    if (!parsed.ok) throw new Error(parsed.errors.join('; '))
    return { ok: true, envelope: parsed.envelope }
  }
  return Object.assign(load, { calls })
}

const NOT_FOUND: LoadResult = { ok: false, error: { kind: 'http', url: './data/x.json', status: 404, statusText: 'Not Found' } }

function withData(artifact: 'fit' | `residuals_${ModelId}`, data: unknown): LoadResult {
  const parsed = parseEnvelope({ ...(fitEnvelope(artifact) as object), data })
  if (!parsed.ok) throw new Error('fixture')
  return { ok: true, envelope: parsed.envelope }
}

describe('loadFit', () => {
  it('parses fit.json, or names it when it fails', async () => {
    const state = await loadFit(fakeLoad())
    expect(state.status === 'ready' && state.fit.models.map((m) => m.id)).toEqual(['aic', 'bic', 'course'])
    expect(await loadFit(fakeLoad({ fit: NOT_FOUND }))).toMatchObject({ status: 'error', artifact: 'fit', error: { kind: 'http' } })
    const bad = await loadFit(fakeLoad({ fit: withData('fit', { sample: 'oos' }) }))
    expect(bad).toMatchObject({ status: 'error', artifact: 'fit', error: { kind: 'contract' } })
    if (bad.status === 'error' && bad.error.kind === 'contract') expect(bad.error.errors).toContain('data.sample: expected "train", got "oos"')
  })
})

describe('loadResiduals', () => {
  it('loads the file of the model asked for, and names that file when it fails', async () => {
    const load = fakeLoad()
    const state = await loadResiduals('bic', load)
    expect(load.calls).toEqual(['residuals_bic'])
    expect(state.status === 'ready' && state.residuals.model_id).toBe('bic')
    expect(await loadResiduals('course', fakeLoad({ residuals_course: NOT_FOUND }))).toMatchObject({ status: 'error', artifact: 'residuals_course', error: { kind: 'http' } })
  })

  it('refuses a file that holds another model’s residuals', async () => {
    const wrong = withData('residuals_bic', { ...((fitEnvelope('residuals_aic') as { data: object }).data) })
    const state = await loadResiduals('bic', fakeLoad({ residuals_bic: wrong }))
    expect(state).toMatchObject({ status: 'error', artifact: 'residuals_bic', error: { kind: 'contract', errors: ['data.model_id: expected "bic", got "aic"'] } })
  })
})

describe('the hooks', () => {
  it('load fit.json and then hold it', async () => {
    const fit = renderHook(() => useFitData(fakeLoad()))
    expect(fit.result.current.status).toBe('loading')
    await waitFor(() => expect(fit.result.current.status).toBe('ready'))
  })

  it('show an error, not "loading" for ever, when reading fit.json throws', async () => {
    const load = async (): Promise<LoadResult> => {
      throw new RangeError('Invalid array length')
    }
    const fit = renderHook(() => useFitData(load))
    await waitFor(() => expect(fit.result.current.status).toBe('error'))
    expect(fit.result.current).toMatchObject({ artifact: 'fit', error: { kind: 'contract', errors: ['could not read the payload: RangeError: Invalid array length'] } })
  })

  it('fetch a residual file again on the next pick after it failed, and keep it once it loads', async () => {
    const failures: Record<string, LoadResult> = { residuals_bic: NOT_FOUND }
    const calls: string[] = []
    const good = fakeLoad()
    const load = async (name: string): Promise<LoadResult> => {
      calls.push(name)
      return failures[name] ?? good(name)
    }
    const hook = renderHook(({ id }: { id: ModelId }) => useResidualsData(id, load), { initialProps: { id: 'bic' as ModelId } })
    await waitFor(() => expect(hook.result.current).toMatchObject({ status: 'error', artifact: 'residuals_bic' }))
    hook.rerender({ id: 'aic' })
    await waitFor(() => expect(hook.result.current.status).toBe('ready'))
    delete failures.residuals_bic // the server is back
    hook.rerender({ id: 'bic' })
    expect(hook.result.current.status).toBe('loading') // the old failure is not shown again
    await waitFor(() => expect(hook.result.current.status === 'ready' && hook.result.current.residuals.model_id).toBe('bic'))
    expect(calls).toEqual(['residuals_bic', 'residuals_aic', 'residuals_bic'])
    hook.rerender({ id: 'aic' })
    hook.rerender({ id: 'bic' })
    expect(calls).toEqual(['residuals_bic', 'residuals_aic', 'residuals_bic']) // kept once it loaded
  })

  it('show an error when reading a residual file throws', async () => {
    const load = async (): Promise<LoadResult> => {
      throw new Error('boom')
    }
    const hook = renderHook(() => useResidualsData('course', load))
    await waitFor(() => expect(hook.result.current).toMatchObject({ status: 'error', artifact: 'residuals_course', error: { errors: ['could not read the payload: Error: boom'] } }))
  })

  it('fetch a residual file only when its model is asked for, and only once', async () => {
    const load = fakeLoad()
    const hook = renderHook(({ id }: { id: ModelId }) => useResidualsData(id, load), { initialProps: { id: 'aic' } })
    expect(hook.result.current.status).toBe('loading')
    await waitFor(() => expect(hook.result.current.status).toBe('ready'))
    expect(load.calls).toEqual(['residuals_aic'])
    hook.rerender({ id: 'course' })
    expect(hook.result.current.status).toBe('loading')
    await waitFor(() => expect(hook.result.current.status === 'ready' && hook.result.current.residuals.model_id).toBe('course'))
    act(() => hook.rerender({ id: 'aic' }))
    expect(hook.result.current.status === 'ready' && hook.result.current.residuals.model_id).toBe('aic')
    expect(load.calls).toEqual(['residuals_aic', 'residuals_course'])
  })
})

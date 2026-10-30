import { describe, expect, it } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { parseEnvelope } from '../lib/contract'
import type { Method, ModelId } from '../lib/contract.forecast'
import { loadEvaluation, loadForecast, useEvaluationData, useForecastFile } from './useForecastData'
import type { LoadResult } from './loadArtifact'
import { forecastEnvelope } from '../test/fixtures/payloads'

/** A fake loader over the made-up envelopes that records every artifact asked for. */
function fakeLoad(overrides: Record<string, LoadResult> = {}) {
  const calls: string[] = []
  const load = async (name: string): Promise<LoadResult> => {
    calls.push(name)
    if (overrides[name]) return overrides[name]
    const parsed = parseEnvelope(forecastEnvelope(name))
    if (!parsed.ok) throw new Error(parsed.errors.join('; '))
    return { ok: true, envelope: parsed.envelope }
  }
  return Object.assign(load, { calls })
}

const NOT_FOUND: LoadResult = { ok: false, error: { kind: 'http', url: './data/x.json', status: 404, statusText: 'Not Found' } }

function withData(artifact: string, data: unknown): LoadResult {
  const parsed = parseEnvelope({ ...(forecastEnvelope(artifact) as object), data })
  if (!parsed.ok) throw new Error('fixture')
  return { ok: true, envelope: parsed.envelope }
}

type Pick = { model: ModelId; method: Method }

describe('loadEvaluation', () => {
  it('parses evaluation.json, or names it when it fails', async () => {
    const state = await loadEvaluation(fakeLoad())
    expect(state.status === 'ready' && state.evaluation.models.map((m) => m.id)).toEqual(['aic', 'bic', 'course'])
    expect(await loadEvaluation(fakeLoad({ evaluation: NOT_FOUND }))).toMatchObject({ status: 'error', artifact: 'evaluation', error: { kind: 'http' } })
    const bad = await loadEvaluation(fakeLoad({ evaluation: withData('evaluation', { alpha: 0.1 }) }))
    expect(bad).toMatchObject({ status: 'error', artifact: 'evaluation', error: { kind: 'contract' } })
    if (bad.status === 'error' && bad.error.kind === 'contract') expect(bad.error.errors).toContain('data.alpha: is 0.1, but this reader reads the tests at alpha 0.05')
  })
})

describe('loadForecast', () => {
  it('loads the file of the model and method asked for, and names that file when it fails', async () => {
    const load = fakeLoad()
    const state = await loadForecast('bic', 'walk_forward', load)
    expect(load.calls).toEqual(['forecast_bic_walk_forward'])
    expect(state.status === 'ready' && [state.forecast.model_id, state.forecast.method]).toEqual(['bic', 'walk_forward'])
    expect(await loadForecast('course', 'static', fakeLoad({ forecast_course_static: NOT_FOUND }))).toMatchObject({ status: 'error', artifact: 'forecast_course_static', error: { kind: 'http' } })
  })

  it('refuses a file that holds another method’s forecast', async () => {
    const wrong = withData('forecast_aic_walk_forward', (forecastEnvelope('forecast_aic_static') as { data: object }).data)
    const state = await loadForecast('aic', 'walk_forward', fakeLoad({ forecast_aic_walk_forward: wrong }))
    expect(state).toMatchObject({ status: 'error', artifact: 'forecast_aic_walk_forward', error: { kind: 'contract', errors: ['data.method: is "static", but this is the file of method "walk_forward"'] } })
  })
})

describe('the hooks', () => {
  it('load evaluation.json and then hold it', async () => {
    const hook = renderHook(() => useEvaluationData(fakeLoad()))
    expect(hook.result.current.status).toBe('loading')
    await waitFor(() => expect(hook.result.current.status).toBe('ready'))
  })

  it('show an error, not "loading" for ever, when reading evaluation.json throws', async () => {
    const load = async (): Promise<LoadResult> => {
      throw new RangeError('Invalid array length')
    }
    const hook = renderHook(() => useEvaluationData(load))
    await waitFor(() => expect(hook.result.current.status).toBe('error'))
    expect(hook.result.current).toMatchObject({ artifact: 'evaluation', error: { kind: 'contract', errors: ['could not read the payload: RangeError: Invalid array length'] } })
  })

  it('fetch a forecast file only when its pair is asked for, and only once', async () => {
    const load = fakeLoad()
    const hook = renderHook(({ model, method }: Pick) => useForecastFile(model, method, load), { initialProps: { model: 'aic', method: 'static' } as Pick })
    expect(hook.result.current.status).toBe('loading')
    await waitFor(() => expect(hook.result.current.status).toBe('ready'))
    expect(load.calls).toEqual(['forecast_aic_static'])
    hook.rerender({ model: 'aic', method: 'refit' })
    expect(hook.result.current.status).toBe('loading')
    await waitFor(() => expect(hook.result.current.status === 'ready' && hook.result.current.forecast.method).toBe('refit'))
    act(() => hook.rerender({ model: 'aic', method: 'static' }))
    expect(hook.result.current.status === 'ready' && hook.result.current.forecast.method).toBe('static')
    expect(load.calls).toEqual(['forecast_aic_static', 'forecast_aic_refit'])
  })

  it('fetch a forecast file again on the next pick after it failed, and keep it once it loads', async () => {
    const failures: Record<string, LoadResult> = { forecast_bic_static: NOT_FOUND }
    const calls: string[] = []
    const good = fakeLoad()
    const load = async (name: string): Promise<LoadResult> => {
      calls.push(name)
      return failures[name] ?? good(name)
    }
    const hook = renderHook(({ model, method }: Pick) => useForecastFile(model, method, load), { initialProps: { model: 'bic', method: 'static' } as Pick })
    await waitFor(() => expect(hook.result.current).toMatchObject({ status: 'error', artifact: 'forecast_bic_static' }))
    hook.rerender({ model: 'bic', method: 'walk_forward' })
    await waitFor(() => expect(hook.result.current.status).toBe('ready'))
    delete failures.forecast_bic_static // the server is back
    hook.rerender({ model: 'bic', method: 'static' })
    expect(hook.result.current.status).toBe('loading') // the old failure is not shown again
    await waitFor(() => expect(hook.result.current.status === 'ready' && hook.result.current.forecast.method).toBe('static'))
    expect(calls).toEqual(['forecast_bic_static', 'forecast_bic_walk_forward', 'forecast_bic_static'])
    hook.rerender({ model: 'bic', method: 'walk_forward' })
    hook.rerender({ model: 'bic', method: 'static' })
    expect(calls).toEqual(['forecast_bic_static', 'forecast_bic_walk_forward', 'forecast_bic_static']) // kept once it loaded
  })

  it('keep a result that arrives late under its own pick, never under the pair on show', async () => {
    // The walk-forward file is held back until the static one has loaded and is on show.
    let release: (r: LoadResult) => void = () => {}
    const good = fakeLoad()
    const calls: string[] = []
    const load = (name: string): Promise<LoadResult> => {
      calls.push(name)
      return name === 'forecast_aic_walk_forward' ? new Promise<LoadResult>((done) => (release = done)) : good(name)
    }
    const method = (state: ReturnType<typeof useForecastFile>) => (state.status === 'ready' ? state.forecast.method : state.status)
    const hook = renderHook(({ model, method }: Pick) => useForecastFile(model, method, load), { initialProps: { model: 'aic', method: 'walk_forward' } as Pick })
    hook.rerender({ model: 'aic', method: 'static' })
    await waitFor(() => expect(method(hook.result.current)).toBe('static'))
    const late = await good('forecast_aic_walk_forward')
    await act(async () => release(late))
    expect(method(hook.result.current)).toBe('static') // the pair on show keeps its own file
    hook.rerender({ model: 'aic', method: 'walk_forward' })
    expect(method(hook.result.current)).toBe('walk_forward') // the late file is there, under its own pick
    expect(calls).toEqual(['forecast_aic_walk_forward', 'forecast_aic_static'])
  })

  it('show an error when reading a forecast file throws', async () => {
    const load = async (): Promise<LoadResult> => {
      throw new Error('boom')
    }
    const hook = renderHook(() => useForecastFile('course', 'walk_forward', load))
    await waitFor(() => expect(hook.result.current).toMatchObject({ status: 'error', artifact: 'forecast_course_walk_forward', error: { errors: ['could not read the payload: Error: boom'] } }))
  })
})

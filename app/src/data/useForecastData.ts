/**
 * Loads the milestone-4 artifacts for the forecast page and parses their payloads: evaluation.json
 * first, then the forecast file of the model and method on show, fetched only when that pair is
 * picked (each is about 0.65 MB; contract.md section 3.9) and kept once loaded. Same three-state
 * shape as the other data hooks; an error names the artifact that failed. A parser that throws
 * becomes an error state too, never a page left loading.
 *
 * Apart from useFitData so that only the forecast page bundles contract.forecast.ts.
 */
import { useEffect, useRef, useState } from 'react'
import type { Envelope } from '../lib/contract'
import { artifactName, parseEvaluation, parseForecast, type Evaluation, type Forecast, type Method, type ModelId } from '../lib/contract.forecast'
import type { ArtifactLoadError } from '../lib/loadError'
import { loadArtifact, type LoadResult } from './loadArtifact'

export type Load = (name: string) => Promise<LoadResult>
type Failure = { status: 'error'; artifact: string; error: ArtifactLoadError }

export type EvaluationState = { status: 'loading' } | Failure | { status: 'ready'; evaluation: Evaluation; envelope: Envelope }
export type ForecastState = { status: 'loading' } | Failure | { status: 'ready'; forecast: Forecast; envelope: Envelope }

/** A thrown error as a failure of `artifact`, so the page shows it instead of loading for ever. */
function thrown(artifact: string, error: unknown): Failure {
  return { status: 'error', artifact, error: { kind: 'contract', errors: [`could not read the payload: ${String(error).slice(0, 200)}`] } }
}

export async function loadEvaluation(load: Load = loadArtifact): Promise<EvaluationState> {
  const res = await load('evaluation')
  if (!res.ok) return { status: 'error', artifact: 'evaluation', error: res.error }
  const parsed = parseEvaluation(res.envelope.data)
  if (!parsed.ok) return { status: 'error', artifact: 'evaluation', error: { kind: 'contract', errors: parsed.errors } }
  return { status: 'ready', evaluation: parsed.evaluation, envelope: res.envelope }
}

/** One forecast file; the parser checks that it holds that model's and method's forecast. */
export async function loadForecast(model: ModelId, method: Method, load: Load = loadArtifact): Promise<ForecastState> {
  const artifact = artifactName(model, method)
  const res = await load(artifact)
  if (!res.ok) return { status: 'error', artifact, error: res.error }
  const parsed = parseForecast(res.envelope.data, model, method)
  if (!parsed.ok) return { status: 'error', artifact, error: { kind: 'contract', errors: parsed.errors } }
  return { status: 'ready', forecast: parsed.forecast, envelope: res.envelope }
}

export function useEvaluationData(load?: Load): EvaluationState {
  const [state, setState] = useState<EvaluationState>({ status: 'loading' })
  useEffect(() => {
    let live = true
    loadEvaluation(load)
      .catch((e: unknown) => thrown('evaluation', e))
      .then((s) => {
        if (live) setState(s)
      })
    return () => {
      live = false
    }
  }, [load])
  return state
}

/**
 * The forecast file of (model, method), requested the first time that pair is asked for and cached
 * for the life of the component, so switching back to a pair does not fetch its file again. A result
 * that arrives after the reader picked another pair is still kept, for when they come back to it. A
 * failure is shown but not kept: the next time that pair is picked, its file is fetched again.
 */
export function useForecastFile(model: ModelId, method: Method, load?: Load): ForecastState {
  const artifact = artifactName(model, method)
  const [cache, setCache] = useState<Partial<Record<string, ForecastState>>>({})
  const requested = useRef(new Set<string>())
  useEffect(() => {
    if (requested.current.has(artifact)) return
    requested.current.add(artifact)
    // A failure from an earlier pick is dropped, so the page reads "loading" while it is fetched again.
    setCache((c) => {
      if (c[artifact] === undefined) return c
      const rest = { ...c }
      delete rest[artifact]
      return rest
    })
    loadForecast(model, method, load)
      .catch((e: unknown) => thrown(artifact, e))
      .then((s) => {
        if (s.status === 'error') requested.current.delete(artifact) // fetch again on the next pick
        setCache((c) => ({ ...c, [artifact]: s }))
      })
  }, [artifact, model, method, load])
  return cache[artifact] ?? { status: 'loading' }
}

/**
 * Loads the milestone-3 artifacts for the fit page and parses their payloads: fit.json first, then
 * the residual file of the model on show, fetched only when that model is picked (each is about
 * 0.5 MB; contract.md section 3.8) and kept once loaded. Same three-state shape as the other data
 * hooks; an error names the artifact that failed. A parser that throws becomes an error state too,
 * never a page left loading.
 *
 * Apart from useOrderData so that only the fit page bundles contract.fit.ts.
 */
import { useEffect, useRef, useState } from 'react'
import type { Envelope } from '../lib/contract'
import { parseFit, parseResiduals, type Fit, type ModelId, type Residuals } from '../lib/contract.fit'
import type { ArtifactLoadError } from '../lib/loadError'
import { loadArtifact, type LoadResult } from './loadArtifact'

export type Load = (name: string) => Promise<LoadResult>
type Failure = { status: 'error'; artifact: string; error: ArtifactLoadError }

export type FitState = { status: 'loading' } | Failure | { status: 'ready'; fit: Fit; envelope: Envelope }
export type ResidualsState = { status: 'loading' } | Failure | { status: 'ready'; residuals: Residuals; envelope: Envelope }

/** A thrown error as a failure of `artifact`, so the page shows it instead of loading for ever. */
function thrown(artifact: string, error: unknown): Failure {
  return { status: 'error', artifact, error: { kind: 'contract', errors: [`could not read the payload: ${String(error).slice(0, 200)}`] } }
}

export async function loadFit(load: Load = loadArtifact): Promise<FitState> {
  const f = await load('fit')
  if (!f.ok) return { status: 'error', artifact: 'fit', error: f.error }
  const fit = parseFit(f.envelope.data)
  if (!fit.ok) return { status: 'error', artifact: 'fit', error: { kind: 'contract', errors: fit.errors } }
  return { status: 'ready', fit: fit.fit, envelope: f.envelope }
}

/** One model's residual file; the parser checks that it holds that model's id. */
export async function loadResiduals(id: ModelId, load: Load = loadArtifact): Promise<ResidualsState> {
  const artifact = `residuals_${id}`
  const res = await load(artifact)
  if (!res.ok) return { status: 'error', artifact, error: res.error }
  const parsed = parseResiduals(res.envelope.data, id)
  if (!parsed.ok) return { status: 'error', artifact, error: { kind: 'contract', errors: parsed.errors } }
  return { status: 'ready', residuals: parsed.residuals, envelope: res.envelope }
}

export function useFitData(load?: Load): FitState {
  const [state, setState] = useState<FitState>({ status: 'loading' })
  useEffect(() => {
    let live = true
    loadFit(load)
      .catch((e: unknown) => thrown('fit', e))
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
 * The residual file of model `id`, requested the first time that id is asked for and cached for the
 * life of the component, so switching back to a model does not fetch its file again. A result that
 * arrives after the reader picked another model is still kept, for when they come back to it. A
 * failure is shown but not kept: the next time that model is picked, its file is fetched again.
 */
export function useResidualsData(id: ModelId, load?: Load): ResidualsState {
  const [cache, setCache] = useState<Partial<Record<ModelId, ResidualsState>>>({})
  const requested = useRef(new Set<ModelId>())
  useEffect(() => {
    if (requested.current.has(id)) return
    requested.current.add(id)
    // A failure from an earlier pick is dropped, so the page reads "loading" while it is fetched again.
    setCache((c) => {
      if (c[id] === undefined) return c
      const rest = { ...c }
      delete rest[id]
      return rest
    })
    loadResiduals(id, load)
      .catch((e: unknown) => thrown(`residuals_${id}`, e))
      .then((s) => {
        if (s.status === 'error') requested.current.delete(id) // fetch again on the next pick
        setCache((c) => ({ ...c, [id]: s }))
      })
  }, [id, load])
  return cache[id] ?? { status: 'loading' }
}

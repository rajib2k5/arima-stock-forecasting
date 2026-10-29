/**
 * Loads the milestone-2 artifacts for the two order-selection pages and parses their payloads.
 * Same three-state shape as useMeta and useExplorerData; an error names the artifact that failed.
 * These files are committed, like every exported file (DATA.md), so a missing one is a real error.
 */
import { useEffect, useState } from 'react'
import type { Envelope } from '../lib/contract'
import { parseAcfPacf, parseAicGrid, parseStationarity, type AcfPacf, type AicGrid, type Stationarity } from '../lib/contract.order'
import type { ArtifactLoadError } from '../lib/loadError'
import { loadArtifact, type LoadResult } from './loadArtifact'

type Load = (name: string) => Promise<LoadResult>
type Failure = { status: 'error'; artifact: string; error: ArtifactLoadError }

export type StationarityState =
  | { status: 'loading' }
  | Failure
  | { status: 'ready'; stationarity: Stationarity; acfPacf: AcfPacf; envelopes: { stationarity: Envelope; acf_pacf: Envelope } }

export type LandscapeState = { status: 'loading' } | Failure | { status: 'ready'; aicGrid: AicGrid; envelope: Envelope }

export async function loadStationarity(load: Load = loadArtifact): Promise<StationarityState> {
  // Both files at once; the first failure (stationarity before acf_pacf) is the one reported.
  const [s, a] = await Promise.all([load('stationarity'), load('acf_pacf')])
  if (!s.ok) return { status: 'error', artifact: 'stationarity', error: s.error }
  const stationarity = parseStationarity(s.envelope.data)
  if (!stationarity.ok) return { status: 'error', artifact: 'stationarity', error: { kind: 'contract', errors: stationarity.errors } }
  if (!a.ok) return { status: 'error', artifact: 'acf_pacf', error: a.error }
  const acfPacf = parseAcfPacf(a.envelope.data)
  if (!acfPacf.ok) return { status: 'error', artifact: 'acf_pacf', error: { kind: 'contract', errors: acfPacf.errors } }
  return { status: 'ready', stationarity: stationarity.stationarity, acfPacf: acfPacf.acfPacf, envelopes: { stationarity: s.envelope, acf_pacf: a.envelope } }
}

export async function loadLandscape(load: Load = loadArtifact): Promise<LandscapeState> {
  const g = await load('aic_grid')
  if (!g.ok) return { status: 'error', artifact: 'aic_grid', error: g.error }
  const grid = parseAicGrid(g.envelope.data)
  if (!grid.ok) return { status: 'error', artifact: 'aic_grid', error: { kind: 'contract', errors: grid.errors } }
  return { status: 'ready', aicGrid: grid.aicGrid, envelope: g.envelope }
}

function useLoaded<T>(loader: (load?: Load) => Promise<T>, load: Load | undefined): T | { status: 'loading' } {
  const [state, setState] = useState<T | { status: 'loading' }>({ status: 'loading' })
  useEffect(() => {
    let live = true
    loader(load).then((s) => {
      if (live) setState(s)
    })
    return () => {
      live = false
    }
  }, [loader, load])
  return state
}

export function useStationarityData(load?: Load): StationarityState {
  return useLoaded(loadStationarity, load) as StationarityState
}

export function useLandscapeData(load?: Load): LandscapeState {
  return useLoaded(loadLandscape, load) as LandscapeState
}

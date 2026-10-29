/**
 * Loads the two artifacts the price explorer draws, `prices` and `eda`, and parses both payloads.
 * Same three-state shape as useMeta; an error names the artifact that failed.
 */
import { useEffect, useState } from 'react'
import type { Envelope } from '../lib/contract'
import { parseEda, parsePrices, type Eda, type Prices } from '../lib/contract.payloads'
import type { ArtifactLoadError } from '../lib/loadError'
import { loadArtifact, type LoadResult } from './loadArtifact'

export type ExplorerState =
  | { status: 'loading' }
  | { status: 'error'; artifact: 'prices' | 'eda'; error: ArtifactLoadError }
  | { status: 'ready'; prices: Prices; eda: Eda; envelopes: { prices: Envelope; eda: Envelope } }

export async function loadExplorer(load: (name: string) => Promise<LoadResult> = loadArtifact): Promise<ExplorerState> {
  // Both files are fetched at once; the first failure (prices before eda) is the one reported.
  const [p, e] = await Promise.all([load('prices'), load('eda')])
  if (!p.ok) return { status: 'error', artifact: 'prices', error: p.error }
  const prices = parsePrices(p.envelope.data)
  if (!prices.ok) return { status: 'error', artifact: 'prices', error: { kind: 'contract', errors: prices.errors } }
  if (!e.ok) return { status: 'error', artifact: 'eda', error: e.error }
  const eda = parseEda(e.envelope.data)
  if (!eda.ok) return { status: 'error', artifact: 'eda', error: { kind: 'contract', errors: eda.errors } }
  return { status: 'ready', prices: prices.prices, eda: eda.eda, envelopes: { prices: p.envelope, eda: e.envelope } }
}

export function useExplorerData(load?: (name: string) => Promise<LoadResult>): ExplorerState {
  const [state, setState] = useState<ExplorerState>({ status: 'loading' })
  useEffect(() => {
    let live = true
    loadExplorer(load).then((s) => {
      if (live) setState(s)
    })
    return () => {
      live = false
    }
  }, [load])
  return state
}

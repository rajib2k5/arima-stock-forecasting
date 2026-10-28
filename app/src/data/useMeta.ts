/**
 * Loads the `meta` artifact once and exposes it as a three-state value the views can render.
 */
import { useEffect, useState } from 'react'
import { parseMeta, type Envelope, type Meta } from '../lib/contract'
import type { ArtifactLoadError } from '../lib/loadError'
import { loadArtifact, type LoadResult } from './loadArtifact'

export type MetaState =
  | { status: 'loading' }
  | { status: 'error'; error: ArtifactLoadError }
  | { status: 'ready'; envelope: Envelope; meta: Meta }

export async function loadMeta(load: (name: string) => Promise<LoadResult> = loadArtifact): Promise<MetaState> {
  const res = await load('meta')
  if (!res.ok) return { status: 'error', error: res.error }
  const meta = parseMeta(res.envelope.data)
  if (!meta.ok) return { status: 'error', error: { kind: 'contract', errors: meta.errors } }
  return { status: 'ready', envelope: res.envelope, meta: meta.meta }
}

export function useMeta(): MetaState {
  const [state, setState] = useState<MetaState>({ status: 'loading' })
  useEffect(() => {
    let live = true
    loadMeta().then((s) => {
      if (live) setState(s)
    })
    return () => {
      live = false
    }
  }, [])
  return state
}

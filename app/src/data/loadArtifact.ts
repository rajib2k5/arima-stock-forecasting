/**
 * The only place the app does I/O for study data: fetch `data/<artifact>.json` and run it
 * through the pure contract parser. Failures come back as typed values, never exceptions.
 */
import { parseEnvelope, type Envelope } from '../lib/contract'
import type { ArtifactLoadError } from '../lib/loadError'

/** The slice of `fetch` this loader needs; the real `fetch` satisfies it, tests pass a fake. */
export type FetchLike = (url: string) => Promise<Pick<Response, 'ok' | 'status' | 'statusText' | 'json'>>

export type LoadResult = { ok: true; envelope: Envelope } | { ok: false; error: ArtifactLoadError }

const ARTIFACT_NAME = /^[a-z][a-z0-9_]*$/

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e))

export async function loadArtifact(name: string, fetchImpl: FetchLike = fetch): Promise<LoadResult> {
  // The name becomes part of a URL path; refuse anything that is not a plain artifact name.
  if (!ARTIFACT_NAME.test(name)) return { ok: false, error: { kind: 'invalid_name', name } }
  // BASE_URL is './' in the built app (vite base), so the data folder resolves next to index.html.
  const url = `${import.meta.env.BASE_URL}data/${name}.json`

  let res: Awaited<ReturnType<FetchLike>>
  try {
    res = await fetchImpl(url)
  } catch (e) {
    return { ok: false, error: { kind: 'network', url, message: messageOf(e) } }
  }
  if (!res.ok) return { ok: false, error: { kind: 'http', url, status: res.status, statusText: res.statusText } }

  let body: unknown
  try {
    body = await res.json()
  } catch (e) {
    return { ok: false, error: { kind: 'json', url, message: messageOf(e) } }
  }

  const parsed = parseEnvelope(body)
  if (!parsed.ok) return { ok: false, error: { kind: 'contract', errors: parsed.errors } }
  if (parsed.envelope.artifact !== name) {
    return { ok: false, error: { kind: 'artifact_mismatch', expected: name, actual: parsed.envelope.artifact } }
  }
  return { ok: true, envelope: parsed.envelope }
}

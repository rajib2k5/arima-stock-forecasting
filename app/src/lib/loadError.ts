/**
 * Typed failures of loading a data artifact, and how to explain each to the reader.
 * The union is built by `src/data/loadArtifact.ts` (I/O) and rendered by the views.
 */

export type ArtifactLoadError =
  | { kind: 'invalid_name'; name: string }
  | { kind: 'network'; url: string; message: string }
  | { kind: 'http'; url: string; status: number; statusText: string }
  | { kind: 'json'; url: string; message: string }
  | { kind: 'contract'; errors: string[] }
  | { kind: 'artifact_mismatch'; expected: string; actual: string }

/** One human-readable line per problem; contract failures list every violation. */
export function describeLoadError(e: ArtifactLoadError): string[] {
  switch (e.kind) {
    case 'invalid_name':
      return [`"${e.name}" is not a valid artifact name (lowercase letters, digits and underscores).`]
    case 'network':
      return [`Could not reach ${e.url}: ${e.message}`]
    case 'http':
      return [`${e.url} answered HTTP ${e.status}${e.statusText ? ` ${e.statusText}` : ''}.`]
    case 'json':
      return [`${e.url} is not valid JSON (${e.message}).`]
    case 'contract':
      return e.errors
    case 'artifact_mismatch':
      return [`Expected the "${e.expected}" artifact but the file says it is "${e.actual}".`]
  }
}

/**
 * True when the failure means "the file is not there": a 404 from a static host, or the HTML page a
 * dev server sends instead of a missing file, which then fails to parse as JSON. The explorer uses
 * it, for held artifacts only, to say "not built in this copy" instead of showing an error.
 */
export function looksAbsent(e: ArtifactLoadError): boolean {
  return (e.kind === 'http' && e.status === 404) || e.kind === 'json'
}

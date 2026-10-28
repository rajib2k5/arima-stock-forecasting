/**
 * Browser capability probes, written so the host objects are injected: tests hand in fakes,
 * the app hands in `document` / `window`. Both probes fail closed (false) on any error.
 */

export interface CanvasHost {
  createElement(tag: 'canvas'): { getContext(contextId: string): unknown }
}

export interface MediaHost {
  matchMedia?: (query: string) => { matches: boolean }
}

/**
 * True when a WebGL2 context can be created. three.js has required WebGL2 since r163, so a
 * browser that only offers WebGL1 cannot run the 3D preview and gets the static fallback.
 */
export function hasWebGL(doc: CanvasHost = document): boolean {
  try {
    return Boolean(doc.createElement('canvas').getContext('webgl2'))
  } catch {
    return false
  }
}

/** True when the reader asked the OS/browser for reduced motion. Absent matchMedia means no. */
export function prefersReducedMotion(win: MediaHost = window): boolean {
  try {
    return win.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  } catch {
    return false
  }
}

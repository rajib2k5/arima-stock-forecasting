/**
 * Guarded browser storage for the theme preference.
 *
 * Every access is guarded: incognito windows or blocked site data must degrade to an in-memory
 * store for the session, never throw. Keys are namespaced `arima:<slug>:<name>` by the callers.
 */

export interface StorageLike {
  getItem(k: string): string | null
  setItem(k: string, v: string): void
  removeItem(k: string): void
}

/**
 * In-memory fallback used when localStorage is missing or blocked (incognito windows,
 * storage-blocking browsers, Node's method-less experimental stub). The preference then
 * still works for the session — it just doesn't persist across reloads.
 */
const memMap = new Map<string, string>()
export const memoryFallback: StorageLike = {
  getItem: (k) => (memMap.has(k) ? (memMap.get(k) as string) : null),
  setItem: (k, v) => void memMap.set(k, v),
  removeItem: (k) => void memMap.delete(k),
}
export function resetMemoryFallback(): void {
  memMap.clear()
}

export function safeStorage(): StorageLike {
  try {
    const s = window.localStorage
    const probe = '__arima_probe__'
    s.setItem(probe, '1')
    s.removeItem(probe)
    return s
  } catch {
    return memoryFallback
  }
}

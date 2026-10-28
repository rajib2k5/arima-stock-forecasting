/**
 * Two themes, 'dark' and 'light'. The active theme is stamped on <html data-theme> so the
 * stylesheet switches token blocks, and the choice persists per app in browser storage.
 */
import { safeStorage, type StorageLike } from './storage'

export type ThemeName = 'dark' | 'light'

const themeKey = (slug: string) => `arima:${slug}:theme`

export function getStoredTheme(slug: string, storage: StorageLike | null = safeStorage()): ThemeName | null {
  try {
    const v = storage?.getItem(themeKey(slug))
    return v === 'dark' || v === 'light' ? v : null
  } catch {
    return null
  }
}

export function setStoredTheme(slug: string, theme: ThemeName, storage: StorageLike | null = safeStorage()): void {
  try {
    storage?.setItem(themeKey(slug), theme)
  } catch {
    /* guarded */
  }
}

export function applyTheme(theme: ThemeName, doc: Document = document): void {
  doc.documentElement.setAttribute('data-theme', theme)
}

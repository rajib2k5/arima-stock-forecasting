/**
 * Small browser-bound hooks for the 3D preview: reduced-motion preference and theme colours.
 * Kept out of `src/lib` because they touch `window` / `document`.
 */
import { useEffect, useState } from 'react'

/** Tracks `prefers-reduced-motion`; `read` is injectable so tests control the first value. */
export function useReducedMotion(read: () => boolean): boolean {
  const [reduced, setReduced] = useState(read)
  useEffect(() => {
    const mq = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
    if (!mq) return
    const on = () => setReduced(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduced
}

export interface ThemeColors {
  ink: string
  muted: string
  accent: string
  line: string
  /** An eligible fit in the AIC landscape. */
  teal: string
  /** A flagged fit (near a unit root) in the AIC landscape. */
  down: string
}

const FALLBACK: ThemeColors = { ink: '#e6e9ef', muted: '#929db0', accent: '#e0a458', line: '#2c3547', teal: '#4fb8a8', down: '#c25450' }

function readThemeColors(): ThemeColors {
  const css = getComputedStyle(document.documentElement)
  const token = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback
  return {
    ink: token('--ink', FALLBACK.ink),
    muted: token('--muted', FALLBACK.muted),
    accent: token('--accent', FALLBACK.accent),
    line: token('--line', FALLBACK.line),
    teal: token('--teal', FALLBACK.teal),
    down: token('--down', FALLBACK.down),
  }
}

/** The CSS colour tokens as plain strings (canvas code cannot read CSS variables), refreshed when the theme flips. */
export function useThemeColors(): ThemeColors {
  const [colors, setColors] = useState(readThemeColors)
  useEffect(() => {
    const mo = new MutationObserver(() => setColors(readThemeColors()))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return colors
}

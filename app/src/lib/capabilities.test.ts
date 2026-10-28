import { describe, expect, it, vi } from 'vitest'
import { hasWebGL, prefersReducedMotion } from './capabilities'

const docWith = (getContext: (id: string) => unknown) => ({ createElement: (tag: 'canvas') => (tag === 'canvas' ? { getContext } : { getContext: () => null }) })

describe('hasWebGL', () => {
  it('is true when a webgl2 context can be created, and asks for exactly "webgl2"', () => {
    const getContext = vi.fn((id: string) => (id === 'webgl2' ? {} : null))
    expect(hasWebGL(docWith(getContext))).toBe(true)
    expect(getContext).toHaveBeenCalledWith('webgl2')
  })
  it('is false when the browser answers null (no WebGL, blocklisted GPU)', () => {
    expect(hasWebGL(docWith(() => null))).toBe(false)
  })
  it('is false when only WebGL1 is available, because three.js needs WebGL2', () => {
    expect(hasWebGL(docWith((id) => (id === 'webgl' ? {} : null)))).toBe(false)
  })
  it('is false, not an exception, when getContext or createElement throws', () => {
    expect(hasWebGL(docWith(() => {
      throw new Error('blocked')
    }))).toBe(false)
    expect(hasWebGL({ createElement: () => { throw new Error('no dom') } })).toBe(false)
  })
  it('is false in jsdom, which has no canvas (setup.ts makes getContext answer null)', () => {
    expect(hasWebGL(document)).toBe(false)
  })
})

describe('prefersReducedMotion', () => {
  it('reads the prefers-reduced-motion media query', () => {
    const matchMedia = vi.fn((q: string) => ({ matches: q === '(prefers-reduced-motion: reduce)' }))
    expect(prefersReducedMotion({ matchMedia })).toBe(true)
    expect(matchMedia).toHaveBeenCalledWith('(prefers-reduced-motion: reduce)')
    expect(prefersReducedMotion({ matchMedia: () => ({ matches: false }) })).toBe(false)
  })
  it('is false when matchMedia is missing (jsdom) or throws', () => {
    expect(prefersReducedMotion({})).toBe(false)
    expect(prefersReducedMotion(window)).toBe(false)
    expect(prefersReducedMotion({ matchMedia: () => { throw new Error('nope') } })).toBe(false)
  })
})

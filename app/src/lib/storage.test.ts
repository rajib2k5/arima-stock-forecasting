import { afterEach, describe, expect, it, vi } from 'vitest'
import { memoryFallback, resetMemoryFallback, safeStorage } from './storage'

afterEach(() => {
  vi.restoreAllMocks()
  resetMemoryFallback()
  window.localStorage.clear()
})

describe('safeStorage', () => {
  it('returns the real localStorage when it works, and leaves no probe key behind', () => {
    expect(safeStorage()).toBe(window.localStorage)
    expect(window.localStorage.length).toBe(0)
  })
  it('falls back to the in-memory store when reading window.localStorage throws', () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(safeStorage()).toBe(memoryFallback)
  })
  it('falls back when localStorage exists but writing throws (quota or incognito mode)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(safeStorage()).toBe(memoryFallback)
  })
})

describe('memoryFallback', () => {
  it('round-trips, reports missing keys as null, and clears on reset', () => {
    expect(memoryFallback.getItem('k')).toBeNull()
    memoryFallback.setItem('k', 'v')
    expect(memoryFallback.getItem('k')).toBe('v')
    memoryFallback.removeItem('k')
    expect(memoryFallback.getItem('k')).toBeNull()
    memoryFallback.setItem('a', '1')
    memoryFallback.setItem('b', '2')
    resetMemoryFallback()
    expect(memoryFallback.getItem('a')).toBeNull()
    expect(memoryFallback.getItem('b')).toBeNull()
  })
})

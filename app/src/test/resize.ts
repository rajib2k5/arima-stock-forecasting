/**
 * A stand-in for ResizeObserver, which jsdom lacks: installed with vi.stubGlobal, it records what is
 * observed, and `resizeTo(px)` reports every observed element as px CSS pixels wide, as a browser
 * does when a phone lays the page out. Callers undo it with vi.unstubAllGlobals().
 */
import { act } from '@testing-library/react'
import { vi } from 'vitest'

export function fakeResizeObserver() {
  const observers = new Set<{ callback: ResizeObserverCallback; targets: Set<Element> }>()
  class FakeResizeObserver {
    private entry: { callback: ResizeObserverCallback; targets: Set<Element> }
    constructor(callback: ResizeObserverCallback) {
      this.entry = { callback, targets: new Set() }
      observers.add(this.entry)
    }
    observe(target: Element) {
      this.entry.targets.add(target)
    }
    unobserve(target: Element) {
      this.entry.targets.delete(target)
    }
    disconnect() {
      observers.delete(this.entry)
    }
  }
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  return {
    /** How many elements are being observed now. */
    observed: () => [...observers].reduce((n, o) => n + o.targets.size, 0),
    resizeTo(px: number) {
      act(() => {
        for (const o of observers) {
          const entries = [...o.targets].map((target) => ({ target, contentRect: { width: px } }) as unknown as ResizeObserverEntry)
          if (entries.length > 0) o.callback(entries, o as unknown as ResizeObserver)
        }
      })
    },
  }
}

/**
 * The price explorer's module must not load until its page opens. A dynamic import() is what
 * makes Vite put the explorer in its own chunk, so the reader of About never downloads it. A
 * static import would load the module as soon as App does; this test would then fail.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { FetchLike } from './data/loadArtifact'
import { withValue } from './test/fixtures/fixtures'

const loads = vi.hoisted(() => ({ count: 0 }))

vi.mock('./views/PriceExplorerView', () => {
  loads.count++
  return { default: () => <p>explorer module loaded</p> }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App: the price explorer is loaded lazily', () => {
  it('does not load the explorer module until the reader opens its page', async () => {
    const meta = withValue(['data', 'artifacts'], ['meta', 'prices', 'eda'])
    vi.stubGlobal('fetch', vi.fn<FetchLike>(async () => ({ ok: true, status: 200, statusText: 'OK', json: async () => meta })))
    const { default: App } = await import('./App')
    render(<App />)
    await screen.findByText('AAPL')
    expect(loads.count).toBe(0)
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'Price explorer' }))
    expect(await screen.findByText('explorer module loaded')).toBeInTheDocument()
    expect(loads.count).toBe(1)
  })
})

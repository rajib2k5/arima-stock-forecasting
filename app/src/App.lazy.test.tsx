/**
 * A data page's module must not load until its page opens (the price explorer, and from milestone 2
 * the stationarity page and the AIC landscape). A dynamic import() is what
 * makes Vite put the explorer in its own chunk, so the reader of About never downloads it. A
 * static import would load the module as soon as App does; this test would then fail.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { FetchLike } from './data/loadArtifact'
import { withValue } from './test/fixtures/fixtures'

const loads = vi.hoisted(() => ({ count: 0, stationarity: 0, landscape: 0 }))

vi.mock('./views/PriceExplorerView', () => {
  loads.count++
  return { default: () => <p>explorer module loaded</p> }
})
vi.mock('./views/StationarityView', () => {
  loads.stationarity++
  return { default: () => <p>stationarity module loaded</p> }
})
vi.mock('./views/AicLandscapeView', () => {
  loads.landscape++
  return { default: () => <p>landscape module loaded</p> }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App: the data pages are loaded lazily', () => {
  it('does not load a page module until the reader opens that page', async () => {
    const meta = withValue(['data', 'artifacts'], ['meta', 'prices', 'eda', 'stationarity', 'acf_pacf', 'aic_grid'])
    vi.stubGlobal('fetch', vi.fn<FetchLike>(async () => ({ ok: true, status: 200, statusText: 'OK', json: async () => meta })))
    const { default: App } = await import('./App')
    render(<App />)
    await screen.findByText('AAPL')
    expect(loads.count).toBe(0)
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'Price explorer' }))
    expect(await screen.findByText('explorer module loaded')).toBeInTheDocument()
    expect(loads.count).toBe(1)
    expect([loads.stationarity, loads.landscape]).toEqual([0, 0])
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'Stationarity' }))
    expect(await screen.findByText('stationarity module loaded')).toBeInTheDocument()
    expect([loads.stationarity, loads.landscape]).toEqual([1, 0])
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'AIC landscape' }))
    expect(await screen.findByText('landscape module loaded')).toBeInTheDocument()
    expect([loads.stationarity, loads.landscape]).toEqual([1, 1])
  })
})

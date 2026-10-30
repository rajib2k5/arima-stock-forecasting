import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import App from './App'
import { resetMemoryFallback, safeStorage } from './lib/storage'
import type { FetchLike } from './data/loadArtifact'
import { validMetaEnvelope, withValue } from './test/fixtures/fixtures'
import { edaEnvelope, fitEnvelope, forecastEnvelope, orderEnvelope, pricesEnvelope } from './test/fixtures/payloads'
import { FORECAST_ARTIFACTS } from './lib/gate'

const STORE = safeStorage()

function stubFetch(body: unknown, init: { ok?: boolean; status?: number; statusText?: string } = {}) {
  const fn = vi.fn<FetchLike>(async () => ({ ok: true, status: 200, statusText: 'OK', ...init, json: async () => body }))
  vi.stubGlobal('fetch', fn)
  return fn
}

beforeEach(() => {
  resetMemoryFallback()
  STORE.removeItem('arima:arima-stock-forecasting:theme')
  window.location.hash = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// Integration: shell + loader + contract parser + About/Architecture views, end to end.
describe('App (integration)', () => {
  it('loads data/meta.json through the contract and renders the study facts on About', async () => {
    const fetchSpy = stubFetch(validMetaEnvelope())
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('ARIMA stock forecasting, done carefully')
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/meta.json…')
    expect(await screen.findByText('AAPL')).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy.mock.calls[0][0].endsWith('data/meta.json')).toBe(true)
    expect(screen.getByText('2015-01-01 to 2023-12-31')).toBeInTheDocument()
    expect(screen.getByText('2024-01-01 to 2026-09-30')).toBeInTheDocument()
    expect(screen.getByLabelText('Data provenance')).toHaveTextContent('schema 1.0.0')
  })

  it('refuses a future major version and says how to regenerate the data', async () => {
    stubFetch(withValue(['schema_version'], '2.0.0'))
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('"2.0.0" has a major version other than 1')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
    expect(screen.queryByText('AAPL')).toBeNull()
  })

  it('shows the same guidance when the data file is missing (404)', async () => {
    stubFetch({}, { ok: false, status: 404, statusText: 'Not Found' })
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('answered HTTP 404')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
  })

  it('navigates to Architecture, which needs no data, and back', async () => {
    stubFetch(validMetaEnvelope())
    render(<App />)
    await screen.findByText('AAPL')
    fireEvent.click(screen.getByRole('link', { name: 'Architecture' }))
    expect(screen.getByRole('img', { name: 'Architecture diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Sequence diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Activity diagram' })).toBeInTheDocument()
    expect(screen.getByText('Empty axes: the AIC landscape page draws the fitted grid on them')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'About' }))
    expect(screen.getByText('AAPL')).toBeInTheDocument()
  })

  it('offers only About and Architecture: no Admin, no Metrics, no key fields', async () => {
    stubFetch(validMetaEnvelope())
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Architecture'])
  })

  it('offers the price explorer once meta lists prices and eda, and loads both only when it opens', async () => {
    const meta = withValue(['data', 'artifacts'], ['meta', 'prices', 'eda'])
    const fn = vi.fn<FetchLike>(async (url) => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => (url.endsWith('data/prices.json') ? pricesEnvelope() : url.endsWith('data/eda.json') ? edaEnvelope() : meta),
    }))
    vi.stubGlobal('fetch', fn)
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Price explorer', 'Architecture'])
    expect(fn).toHaveBeenCalledTimes(1) // only meta.json so far
    fireEvent.click(within(nav).getByRole('link', { name: 'Price explorer' }))
    expect(await screen.findByRole('table', { name: 'Training summary' })).toBeInTheDocument()
    expect(fn.mock.calls.map(([url]) => url.replace(/^.*data\//, '')).sort()).toEqual(['eda.json', 'meta.json', 'prices.json'])
  })

  it('shows a missing data file as a real error, even one an old meta.json lists as held', async () => {
    // Every exported file is committed (DATA.md), so nothing is held any more; a 1.1.x meta.json
    // could still list prices and eda as held, and their absence is then an error like any other.
    let env = withValue(['data', 'artifacts'], ['meta', 'prices', 'eda'])
    ;(env as { data: Record<string, unknown> }).data.held_artifacts = ['prices', 'eda']
    env = { ...(env as object) } as typeof env
    vi.stubGlobal(
      'fetch',
      vi.fn<FetchLike>(async (url) =>
        url.endsWith('data/meta.json')
          ? { ok: true, status: 200, statusText: 'OK', json: async () => env }
          : { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) },
      ),
    )
    render(<App />)
    await screen.findByText('AAPL')
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'Price explorer' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load prices.json.')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
  })

  it('does not offer the price explorer when meta lists only one of its two files', async () => {
    stubFetch(withValue(['data', 'artifacts'], ['meta', 'prices']))
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Architecture'])
  })

  it('offers the two order-selection pages once meta lists their files, and loads each file only when its page opens', async () => {
    const meta = withValue(['data', 'artifacts'], ['meta', 'stationarity', 'acf_pacf', 'aic_grid'])
    const fn = vi.fn<FetchLike>(async (url) => {
      const name = url.replace(/^.*data\//, '').replace('.json', '')
      return { ok: true, status: 200, statusText: 'OK', json: async () => (name === 'meta' ? meta : orderEnvelope(name as 'stationarity' | 'acf_pacf' | 'aic_grid')) }
    })
    vi.stubGlobal('fetch', fn)
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Stationarity', 'AIC landscape', 'Architecture'])
    expect(fn).toHaveBeenCalledTimes(1)
    fireEvent.click(within(nav).getByRole('link', { name: 'Stationarity' }))
    expect(await screen.findByLabelText('Decision on d')).toHaveTextContent('d = 1')
    expect(fn.mock.calls.map(([url]) => url.replace(/^.*data\//, '')).sort()).toEqual(['acf_pacf.json', 'meta.json', 'stationarity.json'])
    fireEvent.click(within(nav).getByRole('link', { name: 'AIC landscape' }))
    expect(await screen.findByLabelText('Chosen model')).toHaveTextContent('ARIMA(0, 1, 1) with a drift')
    expect(fn.mock.calls.map(([url]) => url.replace(/^.*data\//, '')).sort()).toEqual(['acf_pacf.json', 'aic_grid.json', 'meta.json', 'stationarity.json'])
  })

  it('offers the fit page after the AIC landscape once meta lists its four files, and loads fit.json and the primary model’s residuals only when it opens', async () => {
    const meta = withValue(['data', 'artifacts'], ['meta', 'aic_grid', 'fit', 'residuals_aic', 'residuals_bic', 'residuals_course'])
    const fn = vi.fn<FetchLike>(async (url) => {
      const name = url.replace(/^.*data\//, '').replace('.json', '')
      return { ok: true, status: 200, statusText: 'OK', json: async () => (name === 'meta' ? meta : fitEnvelope(name as 'fit' | 'residuals_aic')) }
    })
    vi.stubGlobal('fetch', fn)
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'AIC landscape', 'Fit and diagnostics', 'Architecture'])
    expect(fn).toHaveBeenCalledTimes(1)
    fireEvent.click(within(nav).getByRole('link', { name: 'Fit and diagnostics' }))
    expect(await screen.findByRole('img', { name: /^Standardised residuals of ARIMA\(3, 1, 2\)/ })).toBeInTheDocument()
    expect(fn.mock.calls.map(([url]) => url.replace(/^.*data\//, '')).sort()).toEqual(['fit.json', 'meta.json', 'residuals_aic.json'])
  })

  it('does not offer the fit page when meta lacks one of its residual files', async () => {
    stubFetch(withValue(['data', 'artifacts'], ['meta', 'fit', 'residuals_aic', 'residuals_bic']))
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Architecture'])
  })

  it('offers the forecast page after the fit page once meta lists its eight files, and loads evaluation.json and the first forecast file only when it opens', async () => {
    const meta = withValue(['data', 'artifacts'], ['meta', 'fit', 'residuals_aic', 'residuals_bic', 'residuals_course', ...FORECAST_ARTIFACTS])
    const fn = vi.fn<FetchLike>(async (url) => {
      const name = url.replace(/^.*data\//, '').replace('.json', '')
      return { ok: true, status: 200, statusText: 'OK', json: async () => (name === 'meta' ? meta : forecastEnvelope(name)) }
    })
    vi.stubGlobal('fetch', fn)
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Fit and diagnostics', 'Forecast and evaluation', 'Architecture'])
    expect(fn).toHaveBeenCalledTimes(1)
    fireEvent.click(within(nav).getByRole('link', { name: 'Forecast and evaluation' }))
    expect(await screen.findByRole('img', { name: /^Forecast of AIC choice \(ADR-0002\), Static multi-step/ })).toBeInTheDocument()
    expect(fn.mock.calls.map(([url]) => url.replace(/^.*data\//, '')).sort()).toEqual(['evaluation.json', 'forecast_aic_static.json', 'meta.json'])
  })

  it('does not offer the forecast page when meta lacks one of its eight files', async () => {
    stubFetch(withValue(['data', 'artifacts'], ['meta', ...FORECAST_ARTIFACTS.filter((a) => a !== 'forecast_aic_refit')]))
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Architecture'])
  })

  it('does not offer the stationarity page when meta lists only one of its two files', async () => {
    stubFetch(withValue(['data', 'artifacts'], ['meta', 'stationarity', 'aic_grid']))
    render(<App />)
    await screen.findByText('AAPL')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'AIC landscape', 'Architecture'])
  })

  it('switches between dark and light themes', async () => {
    stubFetch(validMetaEnvelope())
    render(<App />)
    await screen.findByText('AAPL')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
})

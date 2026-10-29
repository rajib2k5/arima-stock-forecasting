import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import PriceExplorerView, { PriceExplorer } from './PriceExplorerView'
import type { ExplorerState } from '../data/useExplorerData'
import { edaEnvelope, fixtureEda, fixturePrices, pricesEnvelope } from '../test/fixtures/payloads'
import type { Envelope } from '../lib/contract'

function ready(): ExplorerState {
  return {
    status: 'ready',
    prices: fixturePrices(),
    eda: fixtureEda(),
    envelopes: { prices: pricesEnvelope() as Envelope, eda: edaEnvelope() as Envelope },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('PriceExplorer', () => {
  it('says it is loading both files', () => {
    render(<PriceExplorer state={{ status: 'loading' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/prices.json and data/eda.json')
  })

  it('names the failing file, lists the problems and says how to regenerate the data', () => {
    const errors = Array.from({ length: 15 }, (_, i) => `problem ${i}`)
    render(<PriceExplorer state={{ status: 'error', artifact: 'eda', error: { kind: 'contract', errors } }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not load eda.json.')
    expect(within(alert).getAllByRole('listitem')).toHaveLength(12)
    expect(alert).toHaveTextContent('…and 3 more.')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
  })

  it('says the data is not built here, and how to build it, when a held file is absent (404)', () => {
    const state: ExplorerState = { status: 'error', artifact: 'prices', error: { kind: 'http', url: './data/prices.json', status: 404, statusText: 'Not Found' } }
    render(<PriceExplorer state={state} held={['prices', 'eda']} />)
    const panel = screen.getByRole('status', { name: 'Data not built here' })
    expect(panel).toHaveTextContent('The price data is not built in this copy.')
    expect(panel).toHaveTextContent('ADR-0001')
    expect(within(panel).getByText('uv run python tools/fetch_prices.py')).toBeInTheDocument()
    expect(within(panel).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows a real error, not "not built", when the missing file is not held or the failure is not an absence', () => {
    const missingPrices: ExplorerState = { status: 'error', artifact: 'prices', error: { kind: 'http', url: 'x', status: 404, statusText: '' } }
    const { unmount } = render(<PriceExplorer state={missingPrices} held={[]} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load prices.json.')
    unmount()
    render(<PriceExplorer state={{ status: 'error', artifact: 'eda', error: { kind: 'http', url: 'x', status: 500, statusText: '' } }} held={['eda']} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load eda.json.')
    expect(screen.queryByRole('status', { name: 'Data not built here' })).toBeNull()
  })

  it('draws the price chart with the three segments shaded and labelled', () => {
    render(<PriceExplorer state={ready()} />)
    const chart = screen.getByRole('img', { name: 'AAPL adjusted close in dollars, 2015-01-02 to 2024-01-02' })
    expect(within(chart).getAllByTestId('plot-band').map((b) => b.getAttribute('class'))).toEqual(['band band-train', 'band band-test', 'band band-oos'])
    const legend = within(screen.getByRole('list', { name: 'Segments' })).getAllByRole('listitem')
    expect(legend.map((li) => li.textContent)).toEqual([
      'Train 2015-01-02 to 2015-01-07 · 4 days',
      'Test 2015-01-08 to 2015-01-08 · 1 day',
      'Out of sample 2024-01-02 to 2024-01-02 · 1 day',
    ])
    expect(screen.getByText(/Forward-filled closes: 2015-01-06\./)).toBeInTheDocument()
  })

  it('switches between the dollar axis and the log axis', () => {
    render(<PriceExplorer state={ready()} />)
    const log = screen.getByRole('radio', { name: 'Log price' })
    expect(log).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(log)
    expect(log).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('img', { name: 'AAPL log of the adjusted close, 2015-01-02 to 2024-01-02' })).toHaveTextContent('log price, ln($)')
    fireEvent.click(screen.getByRole('radio', { name: 'Dollars' }))
    expect(screen.getByRole('img', { name: 'AAPL adjusted close in dollars, 2015-01-02 to 2024-01-02' })).toHaveTextContent('adjusted close ($)')
  })

  it('draws a panel per KDE and per decomposition component', () => {
    render(<PriceExplorer state={ready()} />)
    expect(screen.getByRole('img', { name: 'Kernel density of log price, ln($)' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Kernel density of daily log return' })).toBeInTheDocument()
    for (const part of ['Observed', 'Trend (centred moving average)', 'Seasonal', 'Residual']) {
      expect(screen.getByRole('img', { name: `${part} of the log price` })).toBeInTheDocument()
    }
    expect(screen.getByText(/bandwidth \(scott\) 0\.0138 log points/)).toBeInTheDocument()
    expect(screen.getByText(/undefined for the first 1 and last 1 days/)).toBeInTheDocument()
  })

  it('reads out an undefined trend value as "undefined", not as a number', () => {
    render(<PriceExplorer state={ready()} />)
    const trend = screen.getByRole('img', { name: 'Trend (centred moving average) of the log price' })
    fireEvent.keyDown(trend, { key: 'Home' })
    expect(within(trend).getByTestId('plot-cursor')).toHaveTextContent('2015-01-02 · undefined')
  })

  it('shows the training summary as formatted values from eda.json', () => {
    render(<PriceExplorer state={ready()} />)
    const table = screen.getByRole('table', { name: 'Training summary' })
    expect(table).toHaveTextContent('4 (2015-01-02 to 2015-01-07)')
    expect(table).toHaveTextContent('$23.50 / $23.75 / $23.75 / $24.00')
    expect(table).toHaveTextContent('−1.500')
    expect(screen.getByLabelText('Explorer provenance')).toHaveTextContent('snapshot abababababab')
  })
})

describe('PriceExplorerView (with its data hook)', () => {
  it('fetches prices.json and eda.json and renders the chart', async () => {
    const fetchSpy = vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => (url.endsWith('data/prices.json') ? pricesEnvelope() : edaEnvelope()),
    }))
    vi.stubGlobal('fetch', fetchSpy)
    render(<PriceExplorerView />)
    await waitFor(() => expect(screen.getByRole('table', { name: 'Training summary' })).toBeInTheDocument())
    expect(fetchSpy.mock.calls.map(([url]) => url.replace(/^.*data\//, '')).sort()).toEqual(['eda.json', 'prices.json'])
  })
})

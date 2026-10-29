import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AicLandscapePage } from './AicLandscapeView'
import type { LandscapeState } from '../data/useOrderData'
import type { LandscapeSceneProps } from './AicLandscapeScene'
import { fixtureAicGrid, orderEnvelope } from '../test/fixtures/payloads'
import type { Envelope } from '../lib/contract'

const seen: LandscapeSceneProps[] = []
function StubScene(props: LandscapeSceneProps) {
  seen.push(props)
  return <p>scene for d = {props.d}, trends {props.trends.join(' and ')}</p>
}

function ready(): LandscapeState {
  return { status: 'ready', aicGrid: fixtureAicGrid(), envelope: orderEnvelope('aic_grid') as Envelope }
}

function page(state: LandscapeState = ready(), webgl = true) {
  return render(<AicLandscapePage state={state} webglAvailable={() => webgl} readReducedMotion={() => true} Scene={StubScene} />)
}

afterEach(() => {
  seen.length = 0
  vi.restoreAllMocks()
})

describe('AicLandscapePage', () => {
  it('says it is loading, and names a failed file with the fix', () => {
    const { unmount } = page({ status: 'loading' })
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/aic_grid.json')
    unmount()
    page({ status: 'error', artifact: 'aic_grid', error: { kind: 'http', url: './data/aic_grid.json', status: 404, statusText: 'Not Found' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load aic_grid.json.')
    expect(screen.getByRole('alert')).toHaveTextContent('answered HTTP 404')
  })

  it('names the chosen model, its near ties and what BIC would choose', () => {
    page()
    const card = screen.getByLabelText('Chosen model')
    expect(card).toHaveTextContent('ARIMA(0, 1, 1) with a drift')
    expect(card).toHaveTextContent('AIC −1797.000 with 3 parameters, the lowest of the eligible cells at d = 1.')
    expect(card).toHaveTextContent('ARIMA(1, 1, 0) with a drift (+0.25), ARIMA(0, 1, 1) without a drift (+1.50)')
    // BIC = AIC + k (ln 299 - 2): (0, 1, 1) n is -1795.5 + 2 * 3.70044 = -1788.099, below the AIC choice's
    // -1797.0 + 3 * 3.70044 = -1785.899.
    expect(card).toHaveTextContent('BIC, which charges more per parameter, would choose ARIMA(0, 1, 1) without a drift (BIC −1788.099, against −1785.899')
  })

  it('starts on the chosen d with both of its trends, and shows one d at a time', () => {
    page()
    expect(seen.at(-1)).toMatchObject({ d: 1, trends: ['n', 't'] })
    expect(seen.at(-1)?.motion.autoRotate).toBe(false) // reduced motion asked for
    expect(screen.queryByRole('note')).toBeNull()
    fireEvent.click(screen.getByRole('radio', { name: 'd = 0' }))
    expect(seen.at(-1)).toMatchObject({ d: 0, trends: ['c'] })
    expect(screen.getByRole('note')).toHaveTextContent('This is d = 0. Its AIC values are on their own scale and are never compared with d = 1')
    expect(screen.queryByRole('radiogroup', { name: 'Trend term' })).toBeNull() // d = 0 has one trend only
  })

  it('switches between the two trends of d = 1 and back to both', () => {
    page()
    fireEvent.click(screen.getByRole('radio', { name: 'drift (t)' }))
    expect(seen.at(-1)).toMatchObject({ d: 1, trends: ['t'] })
    expect(screen.getAllByRole('table', { name: /^Delta AIC for d = 1/ })).toHaveLength(1)
    fireEvent.click(screen.getByRole('radio', { name: 'Both' }))
    expect(seen.at(-1)).toMatchObject({ trends: ['n', 't'] })
    expect(screen.getAllByRole('table', { name: /^Delta AIC for d = 1/ })).toHaveLength(2)
  })

  it('tabulates every cell with its status, and marks failures and the choice', () => {
    page()
    const t = screen.getByRole('table', { name: 'Delta AIC for d = 1, drift (t)' })
    const cells = within(t).getAllByRole('cell')
    expect(cells).toHaveLength(4)
    const chosen = cells.find((c) => c.classList.contains('chosen'))!
    expect(chosen).toHaveTextContent('0.0')
    expect(chosen.getAttribute('title')).toBe('ARIMA(0, 1, 1), drift (t): AIC -1797.000; ΔAIC 0.000; ok; the chosen model')
    const failed = cells.find((c) => c.classList.contains('status-failed'))!
    expect(failed).toHaveTextContent('failed')
    const n = screen.getByRole('table', { name: 'Delta AIC for d = 1, no drift (n)' })
    expect(within(n).getAllByRole('cell').find((c) => c.classList.contains('status-not_converged'))).toHaveTextContent('1.8 nc')
    expect(screen.getByText(/d = 1: 6 ok, 1 not converged, 0 near unit root, 1 failed/)).toBeInTheDocument()
  })

  it('shows the best cell of each d, labelled as display only', () => {
    page()
    const table = screen.getByRole('table', { name: 'Best eligible cell of each d' })
    expect(within(table).getAllByRole('row').slice(1).map((r) => r.textContent)).toEqual([
      '0ARIMA(0, 0, 1) with a constant−1100.250',
      '1ARIMA(0, 1, 1) with a drift−1797.000',
      '2ARIMA(1, 2, 0) without a drift−1650.500',
    ])
    expect(screen.getByText('AIC is not used to choose d.')).toBeInTheDocument()
  })

  it('compares pmdarima’s choices with the grid, gap and convergence included', () => {
    page()
    const rows = within(screen.getByRole('table', { name: 'pmdarima cross-check' })).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('courseARIMA(0, 1, 1) with a drift−1796.900yes2yesyes0.100')
    expect(rows[1]).toHaveTextContent('defaultsARIMA(1, 1, 0) without a drift−1795.000no, after 50 iterations1yesno0.250')
  })

  it('says when pmdarima was unavailable', () => {
    const state = ready()
    if (state.status !== 'ready') throw new Error('fixture')
    state.aicGrid.pmdarima_check = { status: 'unavailable', reason: 'ImportError: none', version: null, runs: [] }
    page(state)
    expect(screen.getByText('The pmdarima cross-check is unavailable: ImportError: none.')).toBeInTheDocument()
  })

  it('without WebGL draws no scene and points to the table', () => {
    page(ready(), false)
    expect(seen).toHaveLength(0)
    expect(screen.getByText(/cannot create a WebGL2 context, so the 3D view is not drawn/)).toBeInTheDocument()
  })

  it('falls back to the table when the scene throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    function Broken(): never {
      throw new Error('lost context')
    }
    render(<AicLandscapePage state={ready()} webglAvailable={() => true} readReducedMotion={() => false} Scene={Broken} />)
    expect(screen.getByText(/The 3D view could not start in this browser/)).toBeInTheDocument()
    expect(String(warn.mock.calls[0][1])).toBe('lost context')
  })

  it('names the provenance and the fit settings', () => {
    page()
    expect(screen.getByLabelText('Landscape provenance')).toHaveTextContent('aic_grid: commit ccccccc · statsmodels 0.15.0 · lbfgs, maxiter 200 · near unit root above 0.99 · 300 training rows')
  })
})

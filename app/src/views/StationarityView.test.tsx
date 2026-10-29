import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { StationarityPage } from './StationarityView'
import type { StationarityState } from '../data/useOrderData'
import { fixtureAcfPacf, fixtureStationarity, orderEnvelope } from '../test/fixtures/payloads'
import type { Envelope } from '../lib/contract'

function ready(): StationarityState {
  return {
    status: 'ready',
    stationarity: fixtureStationarity(),
    acfPacf: fixtureAcfPacf(),
    envelopes: { stationarity: orderEnvelope('stationarity') as Envelope, acf_pacf: orderEnvelope('acf_pacf') as Envelope },
  }
}

describe('StationarityPage', () => {
  it('says it is loading both files', () => {
    render(<StationarityPage state={{ status: 'loading' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/stationarity.json and data/acf_pacf.json')
  })

  it('names the failing file and says how to rebuild it', () => {
    render(<StationarityPage state={{ status: 'error', artifact: 'acf_pacf', error: { kind: 'contract', errors: Array.from({ length: 14 }, (_, i) => `p${i}`) } }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not load acf_pacf.json.')
    expect(within(alert).getAllByRole('listitem')).toHaveLength(12)
    expect(alert).toHaveTextContent('…and 2 more.')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
  })

  it('shows the decision, the rule and pmdarima’s answer, all from the file', () => {
    render(<StationarityPage state={ready()} />)
    const card = screen.getByLabelText('Decision on d')
    expect(card).toHaveTextContent('d = 1')
    expect(card).toHaveTextContent('the first difference is the first series on which ADF rejects')
    expect(card).toHaveTextContent('Rule: the smallest d at which ADF rejects and KPSS does not')
    expect(card).toHaveTextContent('pmdarima 2.1.1 ndiffs agrees: KPSS 1, ADF 1, PP 1, all d = 1.')
  })

  it('tabulates both tests for every d and marks the chosen row', () => {
    render(<StationarityPage state={ready()} />)
    const table = screen.getByRole('table', { name: 'ADF and KPSS with a constant' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent('Log price')
    expect(rows[0]).toHaveTextContent('−1.200')
    expect(rows[0]).toHaveTextContent('0.650')
    expect(rows[0]).toHaveTextContent('3 of 0–16')
    expect(rows[0]).toHaveTextContent('≤ 0.01')
    expect(rows[0]).toHaveTextContent('Unit root')
    expect(rows[1]).toHaveAttribute('aria-current', 'true')
    expect(rows[1]).toHaveTextContent('≥ 0.10')
    expect(rows[1]).toHaveTextContent('1.0 × 10^-20')
    const trend = screen.getByRole('table', { name: 'ADF and KPSS with a constant and a trend' })
    expect(within(trend).getAllByRole('row')[2]).toHaveTextContent('0.070')
  })

  it('draws the ACF and PACF of the chosen d first, and of another d on request', () => {
    render(<StationarityPage state={ready()} />)
    expect(screen.getByRole('radio', { name: 'd = 1 (chosen)' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('img', { name: 'ACF of the first difference, lags 1 to 3' })).toBeInTheDocument()
    expect(screen.getByText(/Past the band: 0 of 3 ACF lags and 0 of 3 PACF lags/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'd = 2' }))
    expect(screen.getByRole('img', { name: 'PACF of the second difference, lags 1 to 3' })).toBeInTheDocument()
    // the made-up d = 2 has an ACF of -0.5 at lag 1 and PACFs past the band at lags 1, 2 and 3
    expect(screen.getByText(/Past the band: 1 of 3 ACF lags and 3 of 3 PACF lags/)).toBeInTheDocument()
    expect(screen.getByText(/z \/ √n = 0.1140 at every lag/)).toBeInTheDocument()
  })

  it('names the provenance of both files', () => {
    render(<StationarityPage state={ready()} />)
    expect(screen.getByLabelText('Stationarity provenance')).toHaveTextContent('stationarity: commit ccccccc · acf_pacf: commit ccccccc · 300 training rows')
  })
})

import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { AboutView } from './AboutView'
import { parseEnvelope, parseMeta } from '../lib/contract'
import type { MetaState } from '../data/useMeta'
import { VALID_COMMIT, validMetaEnvelope, withValue } from '../test/fixtures/fixtures'

function ready(env = validMetaEnvelope()): MetaState {
  const e = parseEnvelope(env)
  if (!e.ok) throw new Error(e.errors.join('; '))
  const m = parseMeta(e.envelope.data)
  if (!m.ok) throw new Error(m.errors.join('; '))
  return { status: 'ready', envelope: e.envelope, meta: m.meta }
}

describe('AboutView: copy that does not depend on the data', () => {
  it.each<[string, MetaState]>([
    ['loading', { status: 'loading' }],
    ['error', { status: 'error', error: { kind: 'http', url: './data/meta.json', status: 404, statusText: 'Not Found' } }],
    ['ready', ready()],
  ])('shows the ten-module path, the additions, the credit and the disclaimer while %s', (_name, state) => {
    render(<AboutView state={state} />)
    const path = within(screen.getByRole('list', { name: 'Analysis path' })).getAllByRole('listitem')
    expect(path).toHaveLength(10)
    expect(path[0]).toHaveTextContent('Data acquisition')
    expect(path[3]).toHaveTextContent('Stationarity (ADF)')
    expect(path[4]).toHaveTextContent('ACF/PACF and automatic order search')
    expect(path[5]).toHaveTextContent('90/10 split')
    expect(path[9]).toHaveTextContent('RMSE / MAE / MAPE')
    const adds = within(screen.getByRole('list', { name: 'Additions to the course path' })).getAllByRole('listitem')
    expect(adds.map((li) => li.querySelector('strong')?.textContent)).toEqual([
      'Walk-forward one-step forecasts',
      'A random-walk baseline',
      'KPSS alongside ADF',
      'A "where the sample goes wrong" note',
      'Order selection on the training split only',
    ])
    // The note's description matches the PR/FAQ: the sample course's four mistakes, each costed.
    expect(adds[3]).toHaveTextContent('four places the sample course goes wrong')
    expect(adds[3]).toHaveTextContent('measures what each one costs')
    expect(
      screen.getByText(
        'Module structure follows the "Stock Price Forecasting Using ARIMA Model in Python" sample course outline; all code and text here are our own.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('Not financial advice.')
  })
})

describe('AboutView: loading state', () => {
  it('says it is loading and shows no facts, milestones or provenance', () => {
    render(<AboutView state={{ status: 'loading' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/meta.json…')
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('list', { name: 'Milestones' })).toBeNull()
    expect(screen.queryByLabelText('Data provenance')).toBeNull()
  })
})

describe('AboutView: error state', () => {
  it('tells the reader the command to run and shows what went wrong', () => {
    render(<AboutView state={{ status: 'error', error: { kind: 'http', url: './data/meta.json', status: 404, statusText: 'Not Found' } }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not load the study data.')
    expect(alert).toHaveTextContent('./data/meta.json answered HTTP 404 Not Found.')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByRole('list', { name: 'Milestones' })).toBeNull()
    expect(screen.queryByLabelText('Data provenance')).toBeNull()
  })
  it('lists every contract violation', () => {
    render(<AboutView state={{ status: 'error', error: { kind: 'contract', errors: ['schema_version: major version 2 is not supported (this app reads 1.x.y)', 'data.ticker: missing'] } }} />)
    const items = within(screen.getByRole('alert')).getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toEqual(['schema_version: major version 2 is not supported (this app reads 1.x.y)', 'data.ticker: missing'])
  })
})

describe('AboutView: ready state', () => {
  it('shows the ticker and both windows as inclusive date ranges derived from the contract', () => {
    render(<AboutView state={ready()} />)
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('2015-01-01 to 2023-12-31')).toBeInTheDocument()
    expect(screen.getByText('2024-01-01 to 2026-09-30')).toBeInTheDocument()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })
  it('lists every milestone from the data, with its status as text', () => {
    render(<AboutView state={ready()} />)
    const items = within(screen.getByRole('list', { name: 'Milestones' })).getAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual([
      'Current0. Scaffold, contract and design',
      'Planned1. Data and EDA',
      'Planned2. Stationarity and identification',
    ])
    expect(items[0].querySelector('.badge')).toHaveClass('status-current')
    expect(items[1].querySelector('.badge')).toHaveClass('status-planned')
  })
  it('follows the data, not the template: a done milestone renders as Done', () => {
    // Milestone 0 done and milestone 1 current: the contract allows exactly one "current".
    const env = withValue(['data', 'milestones', 0, 'status'], 'done') as { data: { milestones: { status: string }[] } }
    env.data.milestones[1].status = 'current'
    render(<AboutView state={ready(env)} />)
    const [first, second] = within(screen.getByRole('list', { name: 'Milestones' })).getAllByRole('listitem')
    expect(first).toHaveTextContent('Done')
    expect(first.querySelector('.badge')).toHaveClass('status-done')
    expect(second).toHaveTextContent('Current')
    expect(second.querySelector('.badge')).toHaveClass('status-current')
  })
  it('shows provenance: schema version, generation time and the short commit', () => {
    render(<AboutView state={ready()} />)
    expect(screen.getByLabelText('Data provenance')).toHaveTextContent('schema 1.0.0 · generated 2026-10-28T12:00:00Z · commit 0123456')
    expect(VALID_COMMIT.startsWith('0123456')).toBe(true)
  })
  it('keeps the -dirty marker and shows "uncommitted" as is', () => {
    const { unmount } = render(<AboutView state={ready(withValue(['source_commit'], `${VALID_COMMIT}-dirty`))} />)
    expect(screen.getByLabelText('Data provenance')).toHaveTextContent('commit 0123456-dirty')
    unmount()
    render(<AboutView state={ready(withValue(['source_commit'], 'uncommitted'))} />)
    expect(screen.getByLabelText('Data provenance')).toHaveTextContent('commit uncommitted')
  })
})

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ArchitectureView } from './ArchitectureView'

const diagramText = (name: string) => {
  const svg = screen.getByRole('img', { name })
  return [...svg.querySelectorAll('text')].map((t) => t.textContent ?? '')
}

describe('ArchitectureView', () => {
  it('shows the three diagrams', () => {
    render(<ArchitectureView />)
    expect(screen.getByRole('img', { name: 'Architecture diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Sequence diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Activity diagram' })).toBeInTheDocument()
  })

  it('draws the five layers from source to app, each with its boxes', () => {
    render(<ArchitectureView />)
    const t = diagramText('Architecture diagram')
    expect(t.filter((s) => /^[A-Z ]+$/.test(s))).toEqual(['SOURCE', 'RAW CACHE', 'PYTHON CORE', 'DELIVERY', 'APP'])
    for (const box of [
      'Yahoo Finance via yfinance 1.7.0 · AAPL daily',
      '$VOL_DATA_DIR/arima-stock-forecasting/raw/ · CSV · never committed',
      'data',
      'transforms',
      'stationarity',
      'identification',
      'models',
      'evaluation',
      'export_app_data.py → JSON',
      'build_notebooks.py → .ipynb',
      'reports/',
      'React views: read JSON only',
      'src/lib: pure UI transforms',
    ]) {
      expect(t).toContain(box)
    }
    // the Python core boxes run in pipeline order
    const core = ['data', 'transforms', 'stationarity', 'identification', 'models', 'evaluation'].map((b) => t.indexOf(b))
    expect([...core].sort((a, b) => a - b)).toEqual(core)
  })

  it('spells out each layer in full below the diagram', () => {
    render(<ArchitectureView />)
    expect(screen.getByText('src/arima_forecasting')).toBeInTheDocument()
    expect(screen.getByText('tools/export_app_data.py')).toBeInTheDocument()
    expect(screen.getByText('tools/build_notebooks.py')).toBeInTheDocument()
    expect(screen.getByText('$VOL_DATA_DIR/arima-stock-forecasting/raw/')).toBeInTheDocument()
  })

  it('draws the contract sequence: export, results, write, fetch, parse, typed data, render', () => {
    render(<ArchitectureView />)
    const t = diagramText('Sequence diagram')
    for (const actor of ['export_app_data', 'pipeline', 'disk', 'App', 'contract', 'View']) expect(t).toContain(actor)
    const steps = ['run', 'results', 'write meta.json (envelope)', 'fetch data/meta.json', 'parseEnvelope', 'typed data or errors', 'render']
    const at = steps.map((s) => t.indexOf(s))
    expect(at.every((i) => i >= 0)).toBe(true)
    expect([...at].sort((a, b) => a - b)).toEqual(at)
  })

  it('draws the analysis flow in order, with order selection on the training split only', () => {
    render(<ArchitectureView />)
    const t = diagramText('Activity diagram')
    const flow = [
      'fetch AAPL',
      'clean (ffill)',
      'log transform',
      'ADF + KPSS',
      'difference',
      'ACF/PACF',
      'order search (train only)',
      'fit ARIMA',
      'residual diagnostics',
      'static forecast',
      'walk-forward forecast',
      'random-walk baseline',
      'RMSE / MAE / MAPE',
      'export JSON',
    ]
    expect(t.filter((s) => flow.includes(s))).toEqual(flow)
  })

  it('has the 3D section with its caption and, without WebGL, the static fallback', () => {
    render(<ArchitectureView />)
    expect(screen.getByRole('heading', { name: '3D wiring check' })).toBeInTheDocument()
    expect(screen.getByText('Empty axes: the AIC landscape page draws the fitted grid on them')).toBeInTheDocument()
    expect(screen.getByText('3D preview unavailable.')).toBeInTheDocument()
  })
})

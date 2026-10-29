import { describe, expect, it } from 'vitest'
import { EXPLORER_ARTIFACTS, hasArtifacts, LANDSCAPE_ARTIFACTS, STATIONARITY_ARTIFACTS } from './gate'
import type { Meta } from './contract'

const meta = (artifacts: string[]): Meta => ({
  project: 'p',
  title: 't',
  ticker: 'AAPL',
  windows: { course: { start: '2015-01-01', end_exclusive: '2024-01-01' }, oos: { start: '2024-01-01', end_exclusive: '2026-10-01' } },
  milestones: [{ id: 0, slug: 's', title: 'T', status: 'current' }],
  artifacts,
  held_artifacts: [],
})

describe('hasArtifacts', () => {
  it('needs prices and eda for the explorer', () => {
    expect(EXPLORER_ARTIFACTS).toEqual(['prices', 'eda'])
  })
  it('needs stationarity and acf_pacf for the stationarity page, and aic_grid for the landscape', () => {
    expect(STATIONARITY_ARTIFACTS).toEqual(['stationarity', 'acf_pacf'])
    expect(LANDSCAPE_ARTIFACTS).toEqual(['aic_grid'])
    expect(hasArtifacts(meta(['meta', 'stationarity', 'aic_grid']), STATIONARITY_ARTIFACTS)).toBe(false)
    expect(hasArtifacts(meta(['meta', 'stationarity', 'aic_grid']), LANDSCAPE_ARTIFACTS)).toBe(true)
  })
  it('is true only when every needed artifact is listed', () => {
    expect(hasArtifacts(meta(['meta', 'prices', 'eda']), EXPLORER_ARTIFACTS)).toBe(true)
    expect(hasArtifacts(meta(['meta', 'prices']), EXPLORER_ARTIFACTS)).toBe(false)
    expect(hasArtifacts(meta(['meta']), EXPLORER_ARTIFACTS)).toBe(false)
  })
})

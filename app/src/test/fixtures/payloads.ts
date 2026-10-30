/** Parsed copies of the hand-written payload fixtures (all made-up values), for view and presentation tests. */
import { parseEda, parsePrices, type Eda, type Prices } from '../../lib/contract.payloads'
import pricesData from './prices.data.json'
import edaData from './eda.data.json'
import { parseAcfPacf, parseAicGrid, parseStationarity, type AcfPacf, type AicGrid, type Stationarity } from '../../lib/contract.order'
import stationarityData from './stationarity.data.json'
import acfPacfData from './acf_pacf.data.json'
import aicGridData from './aic_grid.data.json'
import { parseFit, parseResiduals, type Fit, type ModelId, type Residuals } from '../../lib/contract.fit'
import fitData from './fit.data.json'
import residualsAicData from './residuals_aic.data.json'
import { artifactName, parseEvaluation, parseForecast, type Evaluation, type Forecast, type Method, type ModelId as ForecastModelId } from '../../lib/contract.forecast'
import evaluationData from './evaluation.data.json'
import forecastAicStatic from './forecast_aic_static.data.json'
import forecastAicWalkForward from './forecast_aic_walk_forward.data.json'
import forecastAicRefit from './forecast_aic_refit.data.json'
import forecastBicStatic from './forecast_bic_static.data.json'
import forecastBicWalkForward from './forecast_bic_walk_forward.data.json'
import forecastCourseStatic from './forecast_course_static.data.json'
import forecastCourseWalkForward from './forecast_course_walk_forward.data.json'

export function fixturePrices(): Prices {
  const r = parsePrices(structuredClone(pricesData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.prices
}

export function fixtureEda(): Eda {
  const r = parseEda(structuredClone(edaData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.eda
}

export function pricesEnvelope(): unknown {
  return { schema_version: '1.1.0', artifact: 'prices', generated_at: '2026-10-29T12:30:00Z', source_commit: 'b'.repeat(40), data: structuredClone(pricesData) }
}

export function edaEnvelope(): unknown {
  return { schema_version: '1.1.0', artifact: 'eda', generated_at: '2026-10-29T12:30:00Z', source_commit: 'b'.repeat(40), data: structuredClone(edaData) }
}

// ---- milestone 2: made-up order-selection payloads (the shared corpus's bases) ----

export function fixtureStationarity(): Stationarity {
  const r = parseStationarity(structuredClone(stationarityData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.stationarity
}

export function fixtureAcfPacf(): AcfPacf {
  const r = parseAcfPacf(structuredClone(acfPacfData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.acfPacf
}

export function fixtureAicGrid(): AicGrid {
  const r = parseAicGrid(structuredClone(aicGridData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.aicGrid
}

export function orderEnvelope(artifact: 'stationarity' | 'acf_pacf' | 'aic_grid'): unknown {
  const data = { stationarity: stationarityData, acf_pacf: acfPacfData, aic_grid: aicGridData }[artifact]
  return { schema_version: '1.4.0', artifact, generated_at: '2026-10-29T12:30:00Z', source_commit: 'c'.repeat(40), data: structuredClone(data) }
}

// ---- milestone 3: made-up fit and residual payloads (the shared corpus's bases) ----

export function fixtureFit(): Fit {
  const r = parseFit(structuredClone(fitData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.fit
}

/** The made-up residuals of one model: the AIC base, relabelled for BIC and the course model (made up all the same). */
export function residualsData(id: ModelId): Record<string, unknown> {
  return { ...structuredClone(residualsAicData), model_id: id }
}

export function fixtureResiduals(id: ModelId = 'aic'): Residuals {
  const r = parseResiduals(residualsData(id), id)
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.residuals
}

export function fitEnvelope(artifact: 'fit' | `residuals_${ModelId}`): unknown {
  const data = artifact === 'fit' ? structuredClone(fitData) : residualsData(artifact.replace('residuals_', '') as ModelId)
  return { schema_version: '1.4.0', artifact, generated_at: '2026-10-29T12:30:00Z', source_commit: 'd'.repeat(40), data }
}

// ---- milestone 4: made-up forecast and evaluation payloads (run through the Python production code on a simulated series) ----

const FORECAST_DATA: Record<string, unknown> = {
  forecast_aic_static: forecastAicStatic,
  forecast_aic_walk_forward: forecastAicWalkForward,
  forecast_aic_refit: forecastAicRefit,
  forecast_bic_static: forecastBicStatic,
  forecast_bic_walk_forward: forecastBicWalkForward,
  forecast_course_static: forecastCourseStatic,
  forecast_course_walk_forward: forecastCourseWalkForward,
}

/** A fresh copy of one forecast file's made-up payload. */
export function forecastData(model: ForecastModelId, method: Method): Record<string, unknown> {
  return structuredClone(FORECAST_DATA[artifactName(model, method)]) as Record<string, unknown>
}

export function fixtureForecast(model: ForecastModelId = 'aic', method: Method = 'static'): Forecast {
  const r = parseForecast(forecastData(model, method), model, method)
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.forecast
}

export function fixtureEvaluation(): Evaluation {
  const r = parseEvaluation(structuredClone(evaluationData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.evaluation
}

/** The envelope of `evaluation` or of a forecast file, with the made-up payload. */
export function forecastEnvelope(artifact: string): unknown {
  const data = artifact === 'evaluation' ? structuredClone(evaluationData) : structuredClone(FORECAST_DATA[artifact])
  if (data === undefined) throw new Error(`no made-up payload for ${artifact}`)
  return { schema_version: '1.5.0', artifact, generated_at: '2026-10-29T12:30:00Z', source_commit: 'e'.repeat(40), data }
}

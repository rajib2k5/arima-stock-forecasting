/**
 * Which data-driven views the app may offer. `meta.artifacts` lists exactly the files one export
 * wrote (contract.md section 3.1), so a view is switched on only when every file it reads is there.
 * Kept apart from the views themselves so the main bundle does not pull in their code.
 */
import type { Meta } from './contract'

/** The artifacts the price explorer reads. */
export const EXPLORER_ARTIFACTS = ['prices', 'eda'] as const

/** The artifacts the stationarity page reads (milestone 2). */
export const STATIONARITY_ARTIFACTS = ['stationarity', 'acf_pacf'] as const

/** The artifact the AIC landscape reads (milestone 2). */
export const LANDSCAPE_ARTIFACTS = ['aic_grid'] as const

/** The artifacts the fit and diagnostics page reads (milestone 3): fit.json and one residual file per model. */
export const FIT_ARTIFACTS = ['fit', 'residuals_aic', 'residuals_bic', 'residuals_course'] as const

/**
 * The artifacts the forecast and evaluation page reads (milestone 4): the seven forecast files
 * (forecasting.FORECAST_ARTIFACTS, one per model and method) and evaluation.json. Written out, not
 * built from contract.forecast.ts, so that the main bundle does not pull in the forecast parsers.
 */
export const FORECAST_ARTIFACTS = [
  'forecast_aic_static',
  'forecast_aic_walk_forward',
  'forecast_aic_refit',
  'forecast_bic_static',
  'forecast_bic_walk_forward',
  'forecast_course_static',
  'forecast_course_walk_forward',
  'evaluation',
] as const

export function hasArtifacts(meta: Meta, needed: readonly string[]): boolean {
  return needed.every((name) => meta.artifacts.includes(name))
}

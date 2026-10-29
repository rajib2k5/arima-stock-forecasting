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

export function hasArtifacts(meta: Meta, needed: readonly string[]): boolean {
  return needed.every((name) => meta.artifacts.includes(name))
}

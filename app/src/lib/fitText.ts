/**
 * Words and number formats for the fit and diagnostics page. Pure: every value comes from fit.json
 * and residuals_<id>.json. The readings are fixed text keyed by the verdicts Python exported
 * (ADR-0001): nothing here compares a p-value with alpha, or a statistic with anything.
 */
import type { ArchVerdict, CourseTrack, ModelId, NormalityVerdict, SerialVerdict, TrendCode } from './contract.fit'

export const MODEL_LABELS: Record<ModelId, string> = { aic: 'AIC choice', bic: 'BIC choice', course: 'Course model' }

/** "ARIMA(2, 1, 2) with a drift", in the words of the AIC landscape page. */
export function modelName(order: readonly [number, number, number], trend: TrendCode | null): string {
  const tail = trend === 't' ? ' with a drift' : trend === 'c' ? ' with a constant' : trend === 'n' ? ' without a drift' : ''
  return `ARIMA(${order.join(', ')})${tail}`
}

export const EM_DASH = '—'

/** A number to `digits` significant figures, with a true minus sign; null (no inference) as an em dash. */
export function sig(v: number | null, digits = 4): string {
  if (v === null) return EM_DASH
  const text = Math.abs(v).toPrecision(digits)
  return v < 0 && Number(text) !== 0 ? `−${text}` : text
}

/**
 * A p-value for a table, in parts the page sets with a superscript: three decimals from 0.001, a
 * mantissa and a power of ten below it (2.4 × 10⁻⁵⁰), null as an em dash. A p-value of exactly 0 is
 * one that underflowed in double precision (below about 1e-308), so it reads "< 1e-300", never "0".
 * Formatting only: nothing is compared with alpha.
 */
export type PParts = { text: string } | { mantissa: string; exponent: string }

export function pParts(p: number | null): PParts {
  if (p === null) return { text: EM_DASH }
  if (p === 0) return { text: '< 1e-300' }
  if (p >= 0.001) return { text: p.toFixed(3) }
  const [mantissa, exponent] = p.toExponential(1).split('e')
  return { mantissa, exponent: exponent.replace('-', '−') }
}

/** The 95% interval as exported, "[lo, hi]"; null as an em dash. */
export function ciText(lo: number | null, hi: number | null): string {
  return lo === null || hi === null ? EM_DASH : `[${sig(lo)}, ${sig(hi)}]`
}

/** A short badge per verdict, for the test table. */
export const SERIAL_LABELS: Record<SerialVerdict, string> = { found: 'Autocorrelation left', not_found: 'None found', not_tested: 'Not tested' }
export const NORMALITY_LABELS: Record<NormalityVerdict, string> = { rejected: 'Not normal', not_rejected: 'Normal not rejected' }
export const ARCH_LABELS: Record<ArchVerdict, string> = { found: 'Clustering found', not_found: 'None found' }

/** What each Ljung–Box verdict means for the model (concept note 07). */
export const SERIAL_READINGS: Record<SerialVerdict, string> = {
  found:
    'Ljung–Box rejects white noise: at least one lag rejects at 5%, unadjusted for testing several lags. The residuals may still carry autocorrelation that the model has not captured; a rejection near 5% at one lag is weak evidence.',
  not_found: 'Ljung–Box rejects white noise at none of its applied lags: no autocorrelation is left that these lags can detect.',
  not_tested: 'No Ljung–Box lag is above p + q, so the test was applied at no lag: it gives no reading for this model.',
}

export const NORMALITY_READINGS: Record<NormalityVerdict, string> = {
  rejected: 'Jarque–Bera rejects normality: the residuals are skewed or heavier-tailed than a normal, so intervals built on a normal are too narrow in the tails.',
  not_rejected: 'Jarque–Bera does not reject normality: skew and kurtosis are within what a normal sample of this size shows.',
}

export const ARCH_READINGS: Record<ArchVerdict, string> = {
  found: 'ARCH-LM rejects constant variance: large residuals cluster in time (volatility clustering). The mean model can still be right, but its constant-variance intervals are not.',
  not_found: 'ARCH-LM rejects constant variance at none of its lags: no volatility clustering is detected.',
}

/** Concept note 07's prediction, keyed by Python's `confirmed`. */
export const CLUSTERING_READINGS: Record<'true' | 'false', string> = {
  true: 'Confirmed: the residuals of the primary model show volatility clustering, as concept note 07 predicted for daily returns.',
  false: 'Not confirmed: the ARCH-LM test finds no volatility clustering in the residuals of the primary model.',
}

export function clusteringReading(confirmed: boolean): string {
  return CLUSTERING_READINGS[confirmed ? 'true' : 'false']
}

/** The two auto_arima searches compared, keyed by the exported same_order (null: the training-only run is missing). */
export function sameOrderSentence(track: CourseTrack): string {
  const full = modelName(track.full_series.order, track.full_series.trend)
  if (track.same_order === null || track.train_only === null) return `On the full series auto_arima chose ${full}; the training-only run is missing, so there is nothing to compare.`
  const train = modelName(track.train_only.order, track.train_only.trend)
  return track.same_order
    ? `On the full series auto_arima chose ${full}; on the training split alone it chose the same order and intercept, ${train}.`
    : `On the full series auto_arima chose ${full}; on the training split alone it chose ${train}, a different order or intercept.`
}

export function rows(n: number): string {
  return `${n.toLocaleString('en-US')} ${n === 1 ? 'row' : 'rows'}`
}

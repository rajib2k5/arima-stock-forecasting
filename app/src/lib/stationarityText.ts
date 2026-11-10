/**
 * Words and number formats for the stationarity page. Pure: every value comes from
 * stationarity.json; these functions only choose how to write it.
 */
import type { AdfResult, KpssResult, NdiffsCheck, Stationarity, TransformId, Verdict } from './contract.order'

export const TRANSFORM_LABELS: Record<TransformId, string> = {
  log: 'Log price',
  diff1: 'First difference',
  diff2: 'Second difference',
}

export const VERDICT_LABELS: Record<Verdict, string> = {
  stationary: 'Stationary',
  unit_root: 'Unit root',
  conflict: 'Conflict',
  inconclusive: 'Inconclusive',
}

/** What each cell of the 2 x 2 table means, in the words of concept note 05. */
export const VERDICT_MEANINGS: Record<Verdict, string> = {
  stationary: 'ADF rejects a unit root and KPSS does not reject stationarity: no more differencing is needed.',
  unit_root: 'ADF cannot reject a unit root and KPSS rejects stationarity: difference and test again.',
  conflict: 'Both tests reject their null: a break or a root close to 1 can do this. Investigate.',
  inconclusive: 'Neither test rejects: both lack the power to tell, and the data cannot decide.',
}

/**
 * KPSS p-values are clipped to statsmodels' table, so a p at its edge means "this or past it": the
 * sign set before the exported p ("≤ 0.010", "≥ 0.100"), or nothing for a p inside the table. The
 * p itself is set by PValue, as every other p-value on the page.
 */
export function kpssBound(kpss: KpssResult): string {
  if (kpss.p_value_bound === 'smaller') return '≤ '
  if (kpss.p_value_bound === 'greater') return '≥ '
  return ''
}

export function adfLag(adf: AdfResult): string {
  return `${adf.used_lag} of 0–${adf.maxlag}`
}

/** "d = 1" and the reason, read from the file. */
export function decisionSentence(st: Stationarity): string {
  const chosen = st.transforms.find((t) => t.d === st.decision.d_selected)
  const name = chosen ? TRANSFORM_LABELS[chosen.id].toLowerCase() : `d = ${st.decision.d_selected}`
  if (st.decision.tests_conflict) {
    return `No d passed both tests, so d = ${st.decision.d_selected} (the ${name}) is the smallest at which KPSS does not reject. Read the result with care.`
  }
  return `d = ${st.decision.d_selected}: the ${name} is the first series on which ADF rejects a unit root and KPSS does not reject stationarity.`
}

export function ndiffsSentence(nd: NdiffsCheck, dSelected: number): string {
  if (nd.status === 'unavailable') return `pmdarima's cross-check is unavailable: ${nd.reason ?? 'no reason given'}.`
  const values = `KPSS ${nd.kpss}, ADF ${nd.adf}, PP ${nd.pp}`
  return nd.agrees
    ? `pmdarima ${nd.version} ndiffs agrees: ${values}, all d = ${dSelected}.`
    : `pmdarima ${nd.version} ndiffs disagrees: ${values}, against d = ${dSelected}. Its tests are its own implementations (ADR-0002, section 2).`
}

export function signedFixed(value: number, decimals: number): string {
  const text = Math.abs(value).toFixed(decimals)
  return value < 0 && Number(text) !== 0 ? `−${text}` : text
}

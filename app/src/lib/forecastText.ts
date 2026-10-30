/**
 * Words for the forecast and evaluation page, and the pace of its animation. Pure: every number comes from evaluation.json and the
 * forecast files. The readings are fixed text keyed by the verdicts Python exported (ADR-0001):
 * nothing here compares a p-value with alpha, a rate with its level, or a ratio with 1. Each reading
 * says what its test shows and what it does not.
 */
import { DM_SETTINGS, REFIT_EVERY, type CoverageVerdict, type Distribution, type DmVerdict, type Loss, type Method, type WindowId } from './contract.forecast'
import { fmt, pct } from './format'

/** A short badge per Diebold–Mariano verdict. */
export const DM_LABELS: Record<DmVerdict, string> = {
  beats_rw: 'Beats the random walk',
  no_difference: 'No difference found',
  worse_than_rw: 'Worse than the random walk',
  same_as_rw: 'Same as the random walk',
}

/** What each Diebold–Mariano verdict means (HLN-corrected, two-sided, at 5%), and why a model that is the random walk is not tested. */
export const DM_READINGS: Record<DmVerdict, string> = {
  beats_rw:
    'The test rejects equal expected loss at 5%, two-sided, and the model’s mean loss is the lower one: over this window, on this loss, the model forecasts better than yesterday’s price. It says nothing about other windows.',
  no_difference:
    'The test does not reject equal expected loss at 5%, two-sided. That is not evidence that the two forecasts are equally good: on a short or noisy window the test can miss a real difference.',
  worse_than_rw:
    'The test rejects equal expected loss at 5%, two-sided, and the model’s mean loss is the higher one: over this window, on this loss, yesterday’s price is the better forecast. It says nothing about other windows.',
  same_as_rw: `Not tested: this model’s one-step forecasts are the random walk’s, within ${DM_SETTINGS.same_tolerance} log points on every day. An ARIMA(0, 1, 0) without a drift is the random walk, so there is nothing to compare.`,
}

/** A short badge per coverage verdict. */
export const COVERAGE_LABELS: Record<CoverageVerdict, string> = { too_narrow: 'Too narrow', consistent: 'Consistent', too_wide: 'Too wide', not_tested: 'Not tested' }

/** What each coverage verdict means (Kupiec's unconditional coverage test at 5%). */
export const COVERAGE_READINGS: Record<CoverageVerdict, string> = {
  too_narrow: 'Kupiec’s test rejects the nominal level at 5%, and fewer days fall inside than the level says: the interval is too narrow for these days.',
  consistent:
    'Kupiec’s test does not reject the nominal level at 5%: the count inside is within what chance allows. It counts days only; it does not check whether the misses come in clusters.',
  too_wide: 'Kupiec’s test rejects the nominal level at 5%, and more days fall inside than the level says: the interval is wider than these days needed.',
  not_tested:
    'Not tested: a static path is one forecast from one origin, so its days share one accumulated error and are not independent. Kupiec’s test needs independent days, so only the count is shown.',
}

/** Why the static method has no DM result. */
export const DM_STATIC_NOTE =
  'The Diebold–Mariano test is not run for the static method: its forecasts are one path from one origin, a different horizon each day, so the daily loss differences are not the comparable one-step errors the test needs.'

/** What each method does, in a sentence. */
export const METHOD_DESCRIPTIONS: Record<Method, string> = {
  static:
    'One path from the last day before the window: the forecast for day h is h steps ahead, made with the training parameters. This is what the course does.',
  walk_forward: 'Each day is forecast one step ahead, the evening before, from every earlier observation, with the training parameters.',
  refit: `As walk-forward, but the parameters are estimated again every ${REFIT_EVERY} trading days on every observation before that day.`,
}

/** What each window is, in a sentence. */
export const WINDOW_DESCRIPTIONS: Record<WindowId, string> = {
  test: 'The test segment: the last tenth of the course window, after the training rows.',
  oos: 'The out-of-sample window: the frozen period after the course window, used for no choice and no fit.',
}

export const WINDOW_LABELS: Record<WindowId, string> = { test: 'Test', oos: 'Out of sample' }
export const DISTRIBUTION_LABELS: Record<Distribution, string> = { normal: 'Normal', t: 'Student-t (variance-matched)' }
export const LOSS_LABELS: Record<Loss, string> = { squared: 'Squared error', absolute: 'Absolute error' }

/** The back-transform note (PR/FAQ mistake 4): the course's exp(μ) is the median price, not the mean. */
export function backTransformSentence(maxPct: number, meanPct: number): string {
  return `The mean price exp(μ + s²/2) is above the median exp(μ) by up to ${fmt(maxPct, 3)}% on this window (${fmt(meanPct, 3)}% on average). The course reports exp(μ), the median, as "the forecast"; it is not the expected price.`
}

/** A dollar amount. */
export function usd(v: number): string {
  return `$${fmt(v, 2)}`
}

/** "4 of 5 (80.00%)": the exported count and rate, formatted. */
export function insideText(inside: number, n: number, rate: number): string {
  return `${inside} of ${n} (${pct(rate, 1)})`
}

export function days(n: number): string {
  return `${n.toLocaleString('en-US')} ${n === 1 ? 'day' : 'days'}`
}

/** Milliseconds per day of the walk-forward animation: the whole window in about 8 seconds, each day shown 40 to 400 ms. */
export function frameMs(n: number): number {
  return Math.min(400, Math.max(40, Math.round(8000 / Math.max(n, 1))))
}

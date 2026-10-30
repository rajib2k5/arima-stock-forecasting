import { describe, expect, it } from 'vitest'
import { COVERAGE_VERDICTS, DM_VERDICTS, METHODS, WINDOW_IDS } from './contract.forecast'
import {
  backTransformSentence,
  COVERAGE_LABELS,
  COVERAGE_READINGS,
  days,
  DM_LABELS,
  DM_READINGS,
  DM_STATIC_NOTE,
  frameMs,
  insideText,
  METHOD_DESCRIPTIONS,
  usd,
  WINDOW_DESCRIPTIONS,
} from './forecastText'

describe('readings keyed by the exported verdicts', () => {
  it('has one label and one reading per verdict the parser accepts, each different', () => {
    expect(Object.keys(DM_LABELS)).toEqual([...DM_VERDICTS])
    expect(Object.keys(DM_READINGS)).toEqual([...DM_VERDICTS])
    expect(Object.keys(COVERAGE_LABELS)).toEqual([...COVERAGE_VERDICTS])
    expect(Object.keys(COVERAGE_READINGS)).toEqual([...COVERAGE_VERDICTS])
    for (const table of [DM_LABELS, DM_READINGS, COVERAGE_LABELS, COVERAGE_READINGS]) expect(new Set(Object.values(table)).size).toBe(Object.keys(table).length)
  })

  it('says what a DM rejection is about, and that no difference is not equality', () => {
    for (const v of ['beats_rw', 'worse_than_rw'] as const) {
      expect(DM_READINGS[v]).toContain('rejects equal expected loss at 5%, two-sided')
      expect(DM_READINGS[v]).toContain('over this window, on this loss')
      expect(DM_READINGS[v]).toContain('nothing about other windows')
    }
    expect(DM_READINGS.beats_rw).toContain('mean loss is the lower one')
    expect(DM_READINGS.worse_than_rw).toContain('mean loss is the higher one')
    expect(DM_READINGS.no_difference).toContain('does not reject')
    expect(DM_READINGS.no_difference).toContain('not evidence that the two forecasts are equally good')
    expect(DM_STATIC_NOTE).toContain('one path from one origin')
    expect(DM_READINGS.same_as_rw).toContain('forecasts are the random walk’s, within 1e-9 log points on every day')
    expect(DM_READINGS.same_as_rw).toMatch(/^Not tested/)
  })

  it('says what coverage shows, and why a static path is not tested', () => {
    expect(COVERAGE_READINGS.too_narrow).toContain('fewer days fall inside')
    expect(COVERAGE_READINGS.too_wide).toContain('more days fall inside')
    expect(COVERAGE_READINGS.consistent).toContain('does not reject the nominal level at 5%')
    expect(COVERAGE_READINGS.consistent).toContain('does not check whether the misses come in clusters')
    expect(COVERAGE_READINGS.not_tested).toContain('one forecast from one origin')
    expect(COVERAGE_READINGS.not_tested).toContain('not independent')
  })

  it('describes every method and window', () => {
    expect(Object.keys(METHOD_DESCRIPTIONS)).toEqual([...METHODS])
    expect(Object.keys(WINDOW_DESCRIPTIONS)).toEqual([...WINDOW_IDS])
    expect(METHOD_DESCRIPTIONS.refit).toContain('every 21 trading days')
    expect(METHOD_DESCRIPTIONS.static).toContain('what the course does')
  })
})

describe('number formats', () => {
  it('formats the exported numbers and does no arithmetic of the study', () => {
    expect(usd(36.804425014184)).toBe('$36.80')
    expect(usd(1234.5)).toBe('$1,234.50')
    expect(insideText(4, 5, 0.8)).toBe('4 of 5 (80.0%)')
    expect(insideText(0, 20, 0)).toBe('0 of 20 (0.0%)')
    expect(days(1)).toBe('1 day')
    expect(days(690)).toBe('690 days')
    expect(backTransformSentence(0.1179271819396614, 0.06747360371051793)).toBe(
      'The mean price exp(μ + s²/2) is above the median exp(μ) by up to 0.118% on this window (0.067% on average). The course reports exp(μ), the median, as "the forecast"; it is not the expected price.',
    )
  })
})

describe('the animation’s pace', () => {
  it('shows each day 40 to 400 ms, the whole window in about 8 seconds', () => {
    expect([frameMs(5), frameMs(20), frameMs(40), frameMs(690), frameMs(10000), frameMs(0)]).toEqual([400, 400, 200, 40, 40, 400])
  })
})

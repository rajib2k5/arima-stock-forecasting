import { describe, expect, it } from 'vitest'
import { ARCH_READINGS, ciText, clusteringReading, modelName, NORMALITY_READINGS, pParts, rows, sameOrderSentence, SERIAL_READINGS, sig } from './fitText'
import { fixtureFit } from '../test/fixtures/payloads'

describe('number formats', () => {
  it('writes significant figures with a true minus sign, and a dash for a missing value', () => {
    expect(sig(0.0009)).toBe('0.0009000')
    expect(sig(-2.15003, 3)).toBe('−2.15')
    expect(sig(-0.00001, 1)).toBe('−0.00001')
    expect(sig(null)).toBe('—')
    expect(pParts(0.0163)).toEqual({ text: '0.016' })
    expect(pParts(0.001)).toEqual({ text: '0.001' })
    expect(pParts(2.4e-50)).toEqual({ mantissa: '2.4', exponent: '−50' })
    expect(pParts(5.18e-308)).toEqual({ mantissa: '5.2', exponent: '−308' })
    // 0.0 is a p-value that underflowed in double precision: never a bare "0".
    expect(pParts(0)).toEqual({ text: '< 1e-300' })
    expect(pParts(null)).toEqual({ text: '—' })
    expect(ciText(0.11, 1.09)).toBe('[0.1100, 1.090]')
    expect(ciText(null, null)).toBe('—')
    expect(rows(1)).toBe('1 row')
    expect(rows(2264)).toBe('2,264 rows')
  })

  it('names a model by its order and trend', () => {
    expect(modelName([2, 1, 2], 't')).toBe('ARIMA(2, 1, 2) with a drift')
    expect(modelName([1, 0, 0], 'c')).toBe('ARIMA(1, 0, 0) with a constant')
    expect(modelName([0, 1, 1], 'n')).toBe('ARIMA(0, 1, 1) without a drift')
    expect(modelName([0, 1, 1], null)).toBe('ARIMA(0, 1, 1)')
  })
})

describe('readings keyed by the exported verdicts', () => {
  it('has one fixed text per verdict, each different', () => {
    expect(Object.keys(SERIAL_READINGS)).toEqual(['found', 'not_found', 'not_tested'])
    expect(Object.keys(NORMALITY_READINGS)).toEqual(['rejected', 'not_rejected'])
    expect(Object.keys(ARCH_READINGS)).toEqual(['found', 'not_found'])
    expect(new Set(Object.values(SERIAL_READINGS)).size).toBe(3)
    // Any one lag rejecting is enough, and the reading says so.
    expect(SERIAL_READINGS.found).toContain('at least one lag rejects at 5%, unadjusted for testing several lags')
    expect(clusteringReading(true)).toMatch(/^Confirmed/)
    expect(clusteringReading(false)).toMatch(/^Not confirmed/)
  })

  it('compares the two auto_arima searches by the exported same_order', () => {
    const track = fixtureFit().course_track
    expect(sameOrderSentence(track)).toBe(
      'On the full series auto_arima chose ARIMA(0, 1, 1) with a drift; on the training split alone it chose the same order and intercept, ARIMA(0, 1, 1) with a drift.',
    )
    expect(sameOrderSentence({ ...track, train_only: { order: [1, 1, 0], with_intercept: false, trend: 'n' }, same_order: false })).toBe(
      'On the full series auto_arima chose ARIMA(0, 1, 1) with a drift; on the training split alone it chose ARIMA(1, 1, 0) without a drift, a different order or intercept.',
    )
    expect(sameOrderSentence({ ...track, train_only: null, same_order: null })).toMatch(/the training-only run is missing/)
  })
})

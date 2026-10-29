import { describe, expect, it } from 'vitest'
import { adfLag, decisionSentence, formatP, kpssP, ndiffsSentence, signedFixed } from './stationarityText'
import { fixtureStationarity } from '../test/fixtures/payloads'

describe('p-values', () => {
  it('writes three decimals, or powers of ten below 0.001', () => {
    expect(formatP(0.6543)).toBe('0.654')
    expect(formatP(0.001)).toBe('0.001')
    expect(formatP(8.12e-26)).toBe('8.1 × 10^-26')
    expect(formatP(0)).toBe('0')
  })

  it('says "0.01 or less" and "0.10 or more" for a clipped KPSS p-value, and the number otherwise', () => {
    const [log, diff1] = fixtureStationarity().transforms
    expect(kpssP(log.kpss)).toBe('≤ 0.01')
    expect(kpssP(diff1.kpss)).toBe('≥ 0.10')
    expect(kpssP(diff1.with_trend.kpss)).toBe('0.070')
  })

  it('shows the ADF lag against its search range', () => {
    expect(adfLag(fixtureStationarity().transforms[0].adf)).toBe('3 of 0–16')
  })
})

describe('sentences', () => {
  it('names the chosen series and why', () => {
    expect(decisionSentence(fixtureStationarity())).toBe('d = 1: the first difference is the first series on which ADF rejects a unit root and KPSS does not reject stationarity.')
  })

  it('says so plainly when the tests conflict', () => {
    const st = fixtureStationarity()
    st.decision.tests_conflict = true
    expect(decisionSentence(st)).toContain('No d passed both tests, so d = 1 (the first difference)')
  })

  it('reports pmdarima agreeing, disagreeing or unavailable', () => {
    const nd = fixtureStationarity().decision.pmdarima_ndiffs
    expect(ndiffsSentence(nd, 1)).toBe('pmdarima 2.1.1 ndiffs agrees: KPSS 1, ADF 1, PP 1, all d = 1.')
    expect(ndiffsSentence({ ...nd, adf: 2, agrees: false }, 1)).toContain('disagrees: KPSS 1, ADF 2, PP 1, against d = 1')
    expect(ndiffsSentence({ ...nd, status: 'unavailable', reason: 'ImportError: x' }, 1)).toBe("pmdarima's cross-check is unavailable: ImportError: x.")
  })

  it('signs with a real minus and never shows -0', () => {
    expect(signedFixed(-1.2345, 3)).toBe('−1.234')
    expect(signedFixed(-0.0001, 3)).toBe('0.000')
    expect(signedFixed(2, 1)).toBe('2.0')
  })
})

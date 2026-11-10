import { describe, expect, it } from 'vitest'
import { adfLag, decisionSentence, kpssBound, ndiffsSentence, signedFixed } from './stationarityText'
import { fixtureStationarity } from '../test/fixtures/payloads'

describe('p-values', () => {
  it('puts "≤" before a KPSS p clipped at the table’s small edge, "≥" at its large edge, and nothing inside it', () => {
    const [log, diff1] = fixtureStationarity().transforms
    expect(kpssBound(log.kpss)).toBe('≤ ')
    expect(kpssBound(diff1.kpss)).toBe('≥ ')
    expect(kpssBound(diff1.with_trend.kpss)).toBe('')
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

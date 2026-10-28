/**
 * The TypeScript half of the drift guard between the two copies of the envelope rules.
 *
 * The rules live twice: here in `contract.ts`, and in `src/arima_forecasting/contract.py`. This
 * file and `tests/test_contract_corpus.py` both run every case in ONE shared list,
 * `src/test/fixtures/envelope_cases.json`, and assert its `valid` flag. If either side changes a
 * rule without the other, one of the two suites fails on the case where they now disagree.
 *
 * The `valid` flags were written by hand from the contract, not produced by either parser.
 */
import { describe, expect, it } from 'vitest'
import { parseEnvelope } from './contract'
import casesText from '../test/fixtures/envelope_cases.json?raw'

interface Case {
  name: string
  envelope: unknown
  valid: boolean
}

// Parsed with JSON.parse on the raw text, not imported as a JSON module: a module turns the
// literal key "__proto__" into a prototype assignment, and the case that tests it would silently
// become a valid envelope. JSON.parse makes it an ordinary own key, as `res.json()` does.
const CASES = JSON.parse(casesText) as Case[]

describe('envelope_cases.json', () => {
  it('is a real list of cases', () => {
    // A loop over an empty list defines no tests and passes, so an emptied or truncated corpus
    // would go unnoticed without these checks.
    expect(Array.isArray(CASES)).toBe(true)
    expect(CASES.length).toBeGreaterThanOrEqual(100)
    for (const c of CASES) {
      expect(Object.keys(c).sort()).toEqual(['envelope', 'name', 'valid'])
      expect(typeof c.name).toBe('string')
      expect(c.name).not.toBe('')
      expect(typeof c.valid).toBe('boolean')
    }
    const names = CASES.map((c) => c.name)
    expect(new Set(names).size).toBe(names.length)
    expect(CASES.some((c) => c.valid)).toBe(true)
    expect(CASES.some((c) => !c.valid)).toBe(true)
  })

  for (const c of CASES) {
    it(`parseEnvelope agrees: ${c.name}`, () => {
      const result = parseEnvelope(c.envelope)
      expect(result.ok, result.ok ? 'accepted' : `rejected: ${result.errors.join('; ')}`).toBe(c.valid)
    })
  }
})

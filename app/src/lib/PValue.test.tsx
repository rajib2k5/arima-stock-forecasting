import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { PValue } from './PValue'

const shown = (p: number | null) => render(<PValue p={p} />).container

describe('PValue', () => {
  it('writes three decimals from 0.001 up', () => {
    expect(shown(0.0163).textContent).toBe('0.016')
    expect(shown(0.001).textContent).toBe('0.001')
  })

  it('sets a smaller p as a mantissa and a power of ten in a superscript, never "e-" or "10^-" text', () => {
    const p = shown(2.4e-50)
    expect(p.textContent).toBe('2.4 × 10−50')
    expect(p.querySelector('sup')?.textContent).toBe('−50')
    expect(p.textContent).not.toMatch(/e-|\^/)
  })

  it('writes a p that underflowed to 0 as "< 1e-300", and a missing one as a dash, never a bare "0"', () => {
    expect(shown(0).textContent).toBe('< 1e-300')
    expect(shown(null).textContent).toBe('—')
  })
})

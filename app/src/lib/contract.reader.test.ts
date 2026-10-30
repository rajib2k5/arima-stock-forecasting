import { describe, expect, it } from 'vitest'
import { Reader, shown } from './contract.reader'

describe('shown', () => {
  it('quotes a small value as JSON, as the messages always have', () => {
    expect([shown('oos'), shown(4.5), shown(null), shown(true), shown([1, 'a', null]), shown({ a: 1, b: 'x' }), shown(undefined)]).toEqual(['"oos"', '4.5', 'null', 'true', '[1,"a",null]', '{"a":1,"b":"x"}', 'undefined'])
  })

  it('never quotes the whole of a long string, a large array or a large object', () => {
    expect(shown('x'.repeat(81))).toBe(`"${'x'.repeat(80)}"… (81 characters)`)
    expect(shown('x'.repeat(80))).toBe(`"${'x'.repeat(80)}"`)
    expect(shown(new Array(9).fill(0))).toBe('an array of 9')
    expect(shown([[1, 2]])).toBe('an array of 1') // nested: not quoted, however small
    expect(shown(['y'.repeat(41)])).toBe('an array of 1')
    expect(shown(Object.fromEntries(Array.from({ length: 9 }, (_, i) => [`k${i}`, i])))).toBe('an object with 9 keys')
    expect(shown({ a: [1] })).toBe('an object with 1 keys')
  })

  it('keeps a Reader’s message short and quick for a value of any size', () => {
    const r = new Reader()
    const huge = new Array(5_000_000).fill(7)
    const t0 = performance.now()
    expect(r.int(huge, 'data.n')).toBeUndefined()
    expect(r.str({ ...Object.fromEntries(Array.from({ length: 100_000 }, (_, i) => [`k${i}`, i])) }, 'data.label')).toBeUndefined()
    expect(performance.now() - t0).toBeLessThan(1000)
    expect(r.errors).toEqual(['data.n: expected an integer >= 0, got an array of 5000000', 'data.label: expected a non-empty string, got an object with 100000 keys'])
  })
})

import { describe, expect, it } from 'vitest'
import { describeLoadError } from './loadError'

describe('describeLoadError', () => {
  it('names the URL and status for an HTTP failure', () => {
    expect(describeLoadError({ kind: 'http', url: './data/meta.json', status: 404, statusText: 'Not Found' })).toEqual(['./data/meta.json answered HTTP 404 Not Found.'])
    expect(describeLoadError({ kind: 'http', url: 'u', status: 503, statusText: '' })).toEqual(['u answered HTTP 503.'])
  })
  it('explains bad JSON and network failures', () => {
    expect(describeLoadError({ kind: 'json', url: 'u', message: 'Unexpected token <' })).toEqual(['u is not valid JSON (Unexpected token <).'])
    expect(describeLoadError({ kind: 'network', url: 'u', message: 'Failed to fetch' })).toEqual(['Could not reach u: Failed to fetch'])
  })
  it('lists every contract violation, one line each', () => {
    expect(describeLoadError({ kind: 'contract', errors: ['a: missing', 'b: bad'] })).toEqual(['a: missing', 'b: bad'])
  })
  it('explains a wrong artifact and a refused name', () => {
    expect(describeLoadError({ kind: 'artifact_mismatch', expected: 'meta', actual: 'prices' })).toEqual(['Expected the "meta" artifact but the file says it is "prices".'])
    expect(describeLoadError({ kind: 'invalid_name', name: '../x' })).toEqual(['"../x" is not a valid artifact name (lowercase letters, digits and underscores).'])
  })
})

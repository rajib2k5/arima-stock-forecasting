/**
 * Small typed readers shared by the payload parsers (contract.payloads.ts for milestone 1,
 * contract.order.ts for milestone 2). Each method records a path-qualified error and returns
 * undefined on failure, so a parser collects every problem in one pass.
 *
 * In its own module so that each lazily loaded view bundles only the parsers it uses: a module
 * shared by two chunks is bundled whole into a common chunk.
 */
import { BLANK, isIsoDate, isRecord, typeName } from './contract'

/** Small typed readers that record a path-qualified error and return undefined on failure. */
export class Reader {
  readonly errors: string[] = []

  obj(v: unknown, at: string): Record<string, unknown> | undefined {
    if (isRecord(v)) return v
    this.errors.push(`${at}: ${v === undefined ? 'missing' : `expected an object, got ${typeName(v)}`}`)
    return undefined
  }

  field(o: Record<string, unknown>, key: string, at: string): unknown {
    if (Object.hasOwn(o, key)) return o[key]
    this.errors.push(`${at}.${key}: missing`)
    return MISSING
  }

  str(v: unknown, at: string): string | undefined {
    if (v === MISSING) return undefined
    if (typeof v === 'string' && !BLANK.test(v)) return v
    this.errors.push(`${at}: expected a non-empty string, got ${JSON.stringify(v) ?? typeName(v)}`)
    return undefined
  }

  date(v: unknown, at: string): string | undefined {
    const s = this.str(v, at)
    if (s === undefined) return undefined
    if (isIsoDate(s)) return s
    this.errors.push(`${at}: "${s}" is not a calendar date (YYYY-MM-DD)`)
    return undefined
  }

  /** A safe integer >= min: JSON.parse rounds anything beyond +-(2**53 - 1), and Python refuses it too. */
  int(v: unknown, at: string, min = 0): number | undefined {
    if (v === MISSING) return undefined
    if (typeof v === 'number' && Number.isSafeInteger(v) && v >= min) return v
    this.errors.push(`${at}: expected an integer >= ${min}, got ${JSON.stringify(v) ?? typeName(v)}`)
    return undefined
  }

  /** A finite number. JSON.parse turns "1e999" into Infinity, so finiteness is checked here. */
  num(v: unknown, at: string): number | undefined {
    if (v === MISSING) return undefined
    if (typeof v === 'number' && Number.isFinite(v)) return v
    this.errors.push(`${at}: expected a finite number, got ${JSON.stringify(v) ?? typeName(v)}`)
    return undefined
  }

  /** A finite number or null; `undefined` means "invalid", so the caller can tell the cases apart. */
  numOrNull(v: unknown, at: string): number | null | undefined {
    if (v === null) return null
    if (v === MISSING) return undefined
    if (typeof v === 'number' && Number.isFinite(v)) return v
    this.errors.push(`${at}: expected a finite number or null, got ${JSON.stringify(v) ?? typeName(v)}`)
    return undefined
  }

  literal<T extends string | boolean>(v: unknown, expected: T, at: string): T | undefined {
    if (v === MISSING) return undefined
    if (v === expected) return expected
    this.errors.push(`${at}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(v) ?? typeName(v)}`)
    return undefined
  }

  arr(v: unknown, at: string): unknown[] | undefined {
    if (v === MISSING) return undefined
    if (Array.isArray(v)) return v
    this.errors.push(`${at}: expected an array, got ${typeName(v)}`)
    return undefined
  }

  /** true or false; never 1 or "true" (Python's True == 1, so the Python reader checks the type too). */
  bool(v: unknown, at: string): boolean | undefined {
    if (v === MISSING) return undefined
    if (typeof v === 'boolean') return v
    this.errors.push(`${at}: expected true or false, got ${JSON.stringify(v) ?? typeName(v)}`)
    return undefined
  }

  /** One of `options`; with `nullable`, null is returned as null. */
  choice<T extends string>(v: unknown, options: readonly T[], at: string, nullable = false): T | null | undefined {
    if (v === MISSING) return undefined
    if (v === null && nullable) return null
    if (typeof v === 'string' && (options as readonly string[]).includes(v)) return v as T
    this.errors.push(`${at}: expected one of ${options.join(', ')}${nullable ? ' or null' : ''}, got ${JSON.stringify(v) ?? typeName(v)}`)
    return undefined
  }
}

export const MISSING = Symbol('missing')

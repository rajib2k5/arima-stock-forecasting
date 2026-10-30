/**
 * Small typed readers shared by the payload parsers (contract.payloads.ts for milestone 1,
 * contract.order.ts for milestone 2). Each method records a path-qualified error and returns
 * undefined on failure, so a parser collects every problem in one pass.
 *
 * In its own module so that each lazily loaded view bundles only the parsers it uses: a module
 * shared by two chunks is bundled whole into a common chunk.
 */
import { BLANK, isIsoDate, isRecord, problemList, shown, tooMany, typeName } from './contract'

// The one quoting function lives in contract.ts (the envelope's parser uses it too); re-exported for the payload parsers.
export { shown }

/** Small typed readers that record a path-qualified error and return undefined on failure. */
export class Reader {
  /** At most MAX_PROBLEMS: one more throws, and the parser's `capped` ends the list there (contract.ts). */
  readonly errors: string[] = problemList()

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
    this.errors.push(`${at}: expected a non-empty string, got ${shown(v)}`)
    return undefined
  }

  date(v: unknown, at: string): string | undefined {
    const s = this.str(v, at)
    if (s === undefined) return undefined
    if (isIsoDate(s)) return s
    this.errors.push(`${at}: ${shown(s)} is not a calendar date (YYYY-MM-DD)`)
    return undefined
  }

  /** A safe integer >= min: JSON.parse rounds anything beyond +-(2**53 - 1), and Python refuses it too. */
  int(v: unknown, at: string, min = 0): number | undefined {
    if (v === MISSING) return undefined
    if (typeof v === 'number' && Number.isSafeInteger(v) && v >= min) return v
    this.errors.push(`${at}: expected an integer >= ${min}, got ${shown(v)}`)
    return undefined
  }

  /** A finite number. JSON.parse turns "1e999" into Infinity, so finiteness is checked here. */
  num(v: unknown, at: string): number | undefined {
    if (v === MISSING) return undefined
    if (typeof v === 'number' && Number.isFinite(v)) return v
    this.errors.push(`${at}: expected a finite number, got ${shown(v)}`)
    return undefined
  }

  /** A finite number or null; `undefined` means "invalid", so the caller can tell the cases apart. */
  numOrNull(v: unknown, at: string): number | null | undefined {
    if (v === null) return null
    if (v === MISSING) return undefined
    if (typeof v === 'number' && Number.isFinite(v)) return v
    this.errors.push(`${at}: expected a finite number or null, got ${shown(v)}`)
    return undefined
  }

  literal<T extends string | boolean>(v: unknown, expected: T, at: string): T | undefined {
    if (v === MISSING) return undefined
    if (v === expected) return expected
    this.errors.push(`${at}: expected ${JSON.stringify(expected)}, got ${shown(v)}`)
    return undefined
  }

  arr(v: unknown, at: string): unknown[] | undefined {
    if (v === MISSING) return undefined
    if (Array.isArray(v)) return v
    this.errors.push(`${at}: expected an array, got ${typeName(v)}`)
    return undefined
  }

  /** An array of at most `most` items, checked before anyone walks it: a longer one is one short error (payloads._list). */
  list(v: unknown, at: string, most: number, what: string): unknown[] | undefined {
    const items = this.arr(v, at)
    if (items && items.length > most) {
      this.errors.push(tooMany(at, items.length, what, most))
      return undefined
    }
    return items
  }

  /** true or false; never 1 or "true" (Python's True == 1, so the Python reader checks the type too). */
  bool(v: unknown, at: string): boolean | undefined {
    if (v === MISSING) return undefined
    if (typeof v === 'boolean') return v
    this.errors.push(`${at}: expected true or false, got ${shown(v)}`)
    return undefined
  }

  /** One of `options`; with `nullable`, null is returned as null. */
  choice<T extends string>(v: unknown, options: readonly T[], at: string, nullable = false): T | null | undefined {
    if (v === MISSING) return undefined
    if (v === null && nullable) return null
    if (typeof v === 'string' && (options as readonly string[]).includes(v)) return v as T
    this.errors.push(`${at}: expected one of ${options.join(', ')}${nullable ? ' or null' : ''}, got ${shown(v)}`)
    return undefined
  }
}

export const MISSING = Symbol('missing')

/**
 * parsePrices and parseEda against hand-written fixtures (src/test/fixtures/*.data.json). Each
 * test breaks one rule of contract.md sections 3.2-3.3 and checks the exact error path.
 */
import { describe, expect, it } from 'vitest'
import { OOS_MAX_GAP_DAYS, parseEda, parsePrices, TRAIN_FRACTION } from './contract.payloads'
import pricesFixture from '../test/fixtures/prices.data.json'
import edaFixture from '../test/fixtures/eda.data.json'

type Json = null | boolean | number | string | Json[] | { [k: string]: Json }
const prices = (): { [k: string]: Json } => structuredClone(pricesFixture) as { [k: string]: Json }
const eda = (): { [k: string]: Json } => structuredClone(edaFixture) as { [k: string]: Json }

/**
 * `root` with `edit` applied. The edit callback reaches into the payload by path, so it is typed
 * loosely on purpose: a test of a parser has to build payloads the types would forbid.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = any
function edited(root: { [k: string]: Json }, edit: (d: Loose) => void): { [k: string]: Json } {
  edit(root)
  return root
}

const pricesErrors = (data: unknown) => {
  const r = parsePrices(data)
  return r.ok ? [] : r.errors
}
const edaErrors = (data: unknown) => {
  const r = parseEda(data)
  return r.ok ? [] : r.errors
}

describe('parsePrices', () => {
  it('accepts the hand-written fixture and returns its rows and splits', () => {
    const r = parsePrices(prices())
    expect(r.ok ? [] : r.errors).toEqual([])
    if (!r.ok) return
    expect(r.prices.rows).toHaveLength(173) // 4 train, 1 test, and 168 oos rows six days apart from 2024-01-02 to 2026-09-30
    expect(r.prices.rows[4]).toEqual({ date: '2015-01-08', close_usd: 25, log_close: 3.2189, segment: 'test' })
    expect(r.prices.splits.train).toEqual({ start: '2015-01-02', end: '2015-01-07', n: 4 })
    expect(r.prices.fill.filled_dates).toEqual(['2015-01-06'])
    expect(r.prices.source.request.auto_adjust).toBe(true)
  })

  it('ignores unknown keys (the payload is open) and builds a fresh object', () => {
    const data = edited(prices(), (d) => {
      d.notes = 'added in a later minor version'
      d.rows[0].volume = 1
    })
    const r = parsePrices(data)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.prices).not.toHaveProperty('notes')
    expect(r.prices.rows[0]).not.toHaveProperty('volume')
    expect(r.prices.rows).not.toBe(data.rows)
  })

  it('rejects a payload that is not an object', () => {
    expect(pricesErrors([])).toEqual(['data: expected an object, got array'])
  })

  it.each(['ticker', 'price_basis', 'source', 'fill', 'splits', 'rows'])('reports a missing %s', (key) => {
    const data = prices()
    delete data[key]
    expect(pricesErrors(data)).toContain(`data.${key}: missing`)
  })

  it('refuses a price basis other than the adjusted close (a closed enum)', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.price_basis = 'close')))).toEqual(['data.price_basis: expected "adjusted_close", got "close"'])
  })

  it('refuses a raw_sha256 that is not 64 lowercase hex characters', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.source.raw_sha256 = 'AB'.repeat(32))))).toEqual([
      `data.source.raw_sha256: "${'AB'.repeat(32)}" is not 64 lowercase hex characters`,
    ])
  })

  it('refuses a downloaded_at that is not a real UTC time', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.source.downloaded_at = '2026-02-30T12:00:00Z')))).toEqual([
      'data.source.downloaded_at: "2026-02-30T12:00:00Z" is not a UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)',
    ])
  })

  it('refuses a request without auto_adjust, because then Close is not the adjusted close', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.source.request.auto_adjust = false)))).toEqual(['data.source.request.auto_adjust: expected true, got false'])
  })

  it('refuses an empty rows array', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.rows = [])))).toContain('data.rows: must not be empty')
  })

  it('refuses rows that are not strictly ascending by date, including a repeated date', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.rows[2].date = '2015-01-05')))).toContain('data.rows[2].date: 2015-01-05 does not come after 2015-01-05')
    expect(pricesErrors(edited(prices(), (d) => (d.rows[1].date = '2014-12-31')))).toContain('data.rows[1].date: 2014-12-31 does not come after 2015-01-02')
  })

  it('refuses an unknown segment (a closed enum)', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.rows[5].segment = 'holdout')))).toContain('data.rows[5].segment: expected one of train, test, oos, got "holdout"')
  })

  it('refuses segments out of order: a train row after a test row', () => {
    const errors = pricesErrors(
      edited(prices(), (d) => {
        d.rows[3].segment = 'test'
        d.rows[4].segment = 'train'
      }),
    )
    expect(errors).toContain('data.rows[4].segment: "train" after a later segment; expected train, then test, then oos')
  })

  it('refuses a close that is zero, negative or not finite', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.rows[0].close_usd = 0)))).toContain('data.rows[0].close_usd: must be positive, got 0')
    // JSON.parse("1e999") is Infinity, so a finite check is needed even for parsed JSON.
    expect(pricesErrors(edited(prices(), (d) => (d.rows[0].log_close = JSON.parse('1e999'))))).toContain('data.rows[0].log_close: expected a finite number, got null')
  })

  it('refuses splits whose counts or dates disagree with the rows', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.splits.train.n = 5)))).toEqual(['data.splits.train.n: says 5, but 4 rows have segment "train"'])
    expect(pricesErrors(edited(prices(), (d) => (d.splits.oos.end = '2024-01-03')))).toEqual([
      'data.splits.oos: says 2024-01-02 to 2024-01-03, but the rows run 2024-01-02 to 2026-09-30',
    ])
  })

  it('refuses a split whose start is after its end', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.splits.test.start = '2015-01-09')))).toContain('data.splits.test: start 2015-01-09 is after end 2015-01-08')
  })

  it('refuses a train fraction outside (0, 1)', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.splits.train_fraction = 1)))).toEqual(['data.splits.train_fraction: must be between 0 and 1, got 1'])
  })

  it('pins the train fraction at 0.9, config.TRAIN_FRACTION', () => {
    expect(TRAIN_FRACTION).toBe(0.9)
    expect(pricesErrors(edited(prices(), (d) => (d.splits.train_fraction = 0.8)))).toEqual(['data.splits.train_fraction: is 0.8, but this reader splits the course window at 0.9'])
  })

  it('keeps the oos rows inside the pinned out-of-sample window and the course rows before it', () => {
    const window = "but this reader's out-of-sample window is 2024-01-01 to 2026-10-01 (exclusive)"
    const firstOos = (day: string) => (d: Loose) => {
      d.rows[5].date = day
      d.splits.oos.start = day
    }
    const lastOos = (day: string) => (d: Loose) => {
      d.rows[172].date = day
      d.splits.oos.end = day
    }
    expect(pricesErrors(edited(prices(), firstOos('2024-01-01')))).toEqual([]) // the window's first calendar day
    expect(pricesErrors(prices())).toEqual([]) // the fixture's last oos row is the window's last calendar day, 2026-09-30
    expect(pricesErrors(edited(prices(), lastOos('2026-10-01')))).toEqual([`data.splits.oos: runs 2024-01-02 to 2026-10-01, ${window}`])
    expect(pricesErrors(edited(prices(), firstOos('2023-12-29')))).toEqual([
      'data.rows[6].date: 2024-01-08 is 10 calendar days after the oos row before it, 2023-12-29; more than 7 (prep.MAX_GAP_DAYS) means rows are missing',
      `data.splits.oos: runs 2023-12-29 to 2026-09-30, ${window}`,
    ])
    const testDay = (d: Loose) => {
      d.rows[4].date = '2024-01-01'
      d.splits.test.start = '2024-01-01'
      d.splits.test.end = '2024-01-01'
    }
    expect(pricesErrors(edited(prices(), testDay))).toEqual(['data.splits.test.end: is 2024-01-01, but the test rows come before the out-of-sample window, which starts 2024-01-01'])
  })

  it('splits the course window as the producer does: its first int(n x 0.9) rows train, the rest test (prep.train_size)', () => {
    // The last train row labelled test, the split counts rewritten to match: every count agrees with the rows, and only the rule refuses it.
    const moved = (d: Loose) => {
      d.rows[3].segment = 'test'
      d.splits.train.end = '2015-01-06'
      d.splits.train.n = 3
      d.splits.test.start = '2015-01-07'
      d.splits.test.n = 2
    }
    expect(OOS_MAX_GAP_DAYS).toBe(7)
    expect(pricesErrors(edited(prices(), moved))).toEqual([
      "data.rows: 3 rows are train and 2 test, but the course window's 5 rows split at 0.9 give int(5 x 0.9) = 4 train and 1 test (prep.train_size)",
    ])
  })

  it('needs the oos rows to cover the window as the producer checks it: at most 7 calendar days from each end and between rows (prep.check_coverage)', () => {
    const rule = 'more than 7 (prep.MAX_GAP_DAYS) means rows are missing'
    const dropFirst = (d: Loose) => {
      d.rows.splice(5, 1)
      d.splits.oos.start = d.rows[5].date
      d.splits.oos.n = 167
    }
    expect(pricesErrors(edited(prices(), dropFirst))).toEqual([]) // 2024-01-08: 7 days after the start
    const later = (d: Loose) => {
      dropFirst(d)
      d.rows[5].date = '2024-01-09'
      d.splits.oos.start = '2024-01-09'
    }
    expect(pricesErrors(edited(prices(), later))).toEqual([`data.rows[5].date: the first oos row is 2024-01-09, 8 calendar days after the out-of-sample window starts on 2024-01-01; ${rule}`])
    const dropLast = (d: Loose) => {
      d.rows.splice(172, 1)
      d.splits.oos.end = '2026-09-24'
      d.splits.oos.n = 167
    }
    expect(pricesErrors(edited(prices(), dropLast))).toEqual([]) // 7 days before the exclusive end
    const earlier = (d: Loose) => {
      dropLast(d)
      d.rows[171].date = '2026-09-23'
      d.splits.oos.end = '2026-09-23'
    }
    expect(pricesErrors(edited(prices(), earlier))).toEqual([`data.rows[171].date: the last oos row is 2026-09-23, 8 calendar days before the out-of-sample window ends on 2026-10-01 (exclusive); ${rule}`])
    expect(pricesErrors(edited(prices(), (d) => (d.rows[6].date = '2024-01-09')))).toEqual([]) // 7 days apart
    expect(pricesErrors(edited(prices(), (d) => (d.rows[6].date = '2024-01-10')))).toEqual([`data.rows[6].date: 2024-01-10 is 8 calendar days after the oos row before it, 2024-01-02; ${rule}`])
  })

  it('refuses filled dates that are unsorted or not among the rows', () => {
    expect(pricesErrors(edited(prices(), (d) => (d.fill.filled_dates = ['2015-01-07', '2015-01-06'])))).toEqual(['data.fill.filled_dates[1]: dates must be sorted and unique'])
    expect(pricesErrors(edited(prices(), (d) => (d.fill.filled_dates = ['2015-01-03'])))).toEqual(['data.fill.filled_dates[0]: 2015-01-03 is not one of the rows'])
  })

  it('reports every problem in one pass', () => {
    const errors = pricesErrors(
      edited(prices(), (d) => {
        d.ticker = ''
        d.price_basis = 'close'
        d.rows[0].segment = 'x'
        d.fill.method = 'bfill'
      }),
    )
    expect(errors).toEqual([
      'data.ticker: expected a non-empty string, got ""',
      'data.price_basis: expected "adjusted_close", got "close"',
      'data.rows[0].segment: expected one of train, test, oos, got "x"',
      'data.fill.method: expected "ffill", got "bfill"',
    ])
  })
})

describe('parseEda', () => {
  it('accepts the hand-written fixture', () => {
    const r = parseEda(eda())
    expect(r.ok ? [] : r.errors).toEqual([])
    if (!r.ok) return
    expect(r.eda.kdes.map((k) => k.variable)).toEqual(['log_close', 'log_return'])
    expect(r.eda.decomposition.rows[0].trend_log).toBeNull()
    expect(r.eda.decomposition.rows[1].trend_log).toBe(3.1623)
    expect(r.eda.summary.log_return.excess_kurtosis).toBe(-1.5)
  })

  it('accepts a KDE of a variable it does not know (an open enum)', () => {
    const data = edited(eda(), (d) => d.kdes.push({ ...structuredClone(d.kdes[0]), variable: 'close_usd' }))
    const r = parseEda(data)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.eda.kdes.map((k) => k.variable)).toEqual(['log_close', 'log_return', 'close_usd'])
  })

  it('refuses a sample other than train: EDA describes the training split only', () => {
    expect(edaErrors(edited(eda(), (d) => (d.sample = 'course')))).toEqual(['data.sample: expected "train", got "course"'])
  })

  it('refuses a payload without the log-return KDE, or with two KDEs of one variable', () => {
    expect(edaErrors(edited(eda(), (d) => d.kdes.pop()))).toEqual(['data.kdes: no KDE for "log_return"'])
    expect(edaErrors(edited(eda(), (d) => (d.kdes[1].variable = 'log_close')))).toEqual([
      'data.kdes: no KDE for "log_return"',
      'data.kdes: duplicate variables: "log_close" appears more than once',
    ])
  })

  it('refuses KDE points that are not ascending in x, or a negative density', () => {
    expect(edaErrors(edited(eda(), (d) => (d.kdes[0].points[2].x = 3.17)))).toEqual(['data.kdes[0].points[2].x: 3.17 does not come after 3.17'])
    expect(edaErrors(edited(eda(), (d) => (d.kdes[1].points[0].normal_density = -0.1)))).toEqual(['data.kdes[1].points[0].normal_density: must not be negative, got -0.1'])
  })

  it('refuses a bandwidth that is not positive, and fewer than two points', () => {
    expect(edaErrors(edited(eda(), (d) => (d.kdes[0].bandwidth = 0)))).toEqual(['data.kdes[0].bandwidth: must be positive, got 0'])
    expect(edaErrors(edited(eda(), (d) => (d.kdes[0].points = [d.kdes[0].points[0]])))).toEqual(['data.kdes[0].points: expected at least 2 points, got 1'])
  })

  it('refuses a multiplicative decomposition (the model is a closed enum, "additive")', () => {
    expect(edaErrors(edited(eda(), (d) => (d.decomposition.model = 'multiplicative')))).toEqual(['data.decomposition.model: expected "additive", got "multiplicative"'])
  })

  it('accepts null only in the nullable fields, and only together', () => {
    expect(edaErrors(edited(eda(), (d) => (d.decomposition.rows[0].resid_log = 0.1)))).toEqual(['data.decomposition.rows[0]: trend_log and resid_log must be null on the same rows'])
    expect(edaErrors(edited(eda(), (d) => (d.decomposition.rows[1].seasonal_log = null)))).toEqual(['data.decomposition.rows[1].seasonal_log: expected a finite number, got null'])
    expect(edaErrors(edited(eda(), (d) => (d.decomposition.rows[1].trend_log = 'n/a')))).toEqual(['data.decomposition.rows[1].trend_log: expected a finite number or null, got "n/a"'])
  })

  it('refuses decomposition rows that do not cover the summary period', () => {
    // Drop the last row and keep the null pattern valid (rows 0 and 2 null), so only coverage fails.
    const short = edited(eda(), (d) => {
      d.decomposition.rows.pop()
      d.decomposition.rows[2].trend_log = null
      d.decomposition.rows[2].resid_log = null
    })
    expect(edaErrors(short)).toEqual([
      'data.decomposition.rows: 3 rows from 2015-01-02 to 2015-01-06, but the summary covers 4 rows from 2015-01-02 to 2015-01-07',
    ])
  })

  it('refuses nulls anywhere but the first and last period // 2 rows, and names the first bad row', () => {
    const middle = edited(eda(), (d) => {
      d.decomposition.rows[1].trend_log = null
      d.decomposition.rows[1].resid_log = null
    })
    expect(edaErrors(middle)).toEqual([
      'data.decomposition.rows: trend_log must be null on exactly the first and last 1 rows (period 2 // 2), and nowhere else; row 1 breaks this',
    ])
  })

  it('refuses summary.log_return.n other than summary.n - 1, and integers below their minimum', () => {
    expect(edaErrors(edited(eda(), (d) => (d.summary.log_return.n = 5)))).toEqual(['data.summary.log_return.n: is 5, but data.summary.n - 1 is 3'])
    expect(edaErrors(edited(eda(), (d) => (d.decomposition.period = 1)))).toEqual(['data.decomposition.period: expected an integer >= 2, got 1'])
    expect(edaErrors(edited(eda(), (d) => (d.kdes[0].n = 1)))).toEqual(['data.kdes[0].n: expected an integer >= 2, got 1'])
    expect(pricesErrors(edited(prices(), (d) => (d.source.raw_rows = 0)))).toEqual(['data.source.raw_rows: expected an integer >= 1, got 0'])
    expect(pricesErrors(edited(prices(), (d) => (d.source.raw_rows = 2 ** 53)))).toEqual([`data.source.raw_rows: expected an integer >= 1, got ${2 ** 53}`])
  })

  it('refuses a summary whose start is not before its end, and a missing moment', () => {
    expect(edaErrors(edited(eda(), (d) => (d.summary.start = '2015-01-07')))).toContain('data.summary: start 2015-01-07 must be before end 2015-01-07')
    expect(edaErrors(edited(eda(), (d) => delete d.summary.log_return.skew))).toEqual(['data.summary.log_return.skew: missing'])
  })

  it('rejects a payload that is not an object, and reports missing sections', () => {
    expect(edaErrors('eda')).toEqual(['data: expected an object, got string'])
    expect(edaErrors({ sample: 'train' })).toEqual(['data.summary: missing', 'data.kdes: missing', 'data.decomposition: missing'])
  })
})

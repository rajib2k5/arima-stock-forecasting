import { describe, expect, it } from 'vitest'
import { dayBefore, formatWindow, shortCommit, statusLabel } from './present'

const SHA = '0123456789abcdef0123456789abcdef01234567'
const SHA256 = '0123456789abcdef'.repeat(4) // 16 hex characters x 4 = 64: a SHA-256 repository's commit id

describe('shortCommit', () => {
  it('keeps the first 7 hex characters of a clean commit', () => {
    expect(shortCommit(SHA)).toBe('0123456')
  })
  it('keeps the -dirty marker', () => {
    expect(shortCommit(`${SHA}-dirty`)).toBe('0123456-dirty')
  })
  it('shortens a 64-hex SHA-256 commit the same way, with or without -dirty', () => {
    expect(shortCommit(SHA256)).toBe('0123456')
    expect(shortCommit(`${SHA256}-dirty`)).toBe('0123456-dirty')
  })
  it('passes "uncommitted" and anything unrecognised through unchanged', () => {
    expect(shortCommit('uncommitted')).toBe('uncommitted')
    expect(shortCommit('abc')).toBe('abc')
  })
})

describe('dayBefore (hand-worked calendar cases)', () => {
  it('crosses a year boundary: 2024-01-01 -> 2023-12-31', () => {
    expect(dayBefore('2024-01-01')).toBe('2023-12-31')
  })
  it('crosses a month boundary: 2026-10-01 -> 2026-09-30', () => {
    expect(dayBefore('2026-10-01')).toBe('2026-09-30')
  })
  it('lands on 29 February in a leap year and 28 in a common year', () => {
    expect(dayBefore('2024-03-01')).toBe('2024-02-29')
    expect(dayBefore('2023-03-01')).toBe('2023-02-28')
  })
  it('subtracts within a month', () => {
    expect(dayBefore('2026-10-15')).toBe('2026-10-14')
  })
  it('keeps years 0001-0099 as they are (Date.UTC would read them as 1901-1999)', () => {
    // contract.ts accepts these dates, so display must not move them by 1900 years.
    expect(dayBefore('0099-03-01')).toBe('0099-02-28')
    expect(dayBefore('0100-01-01')).toBe('0099-12-31')
    expect(dayBefore('0004-03-01')).toBe('0004-02-29') // year 4 is a leap year
    expect(dayBefore('0050-06-15')).toBe('0050-06-14')
  })
  it('refuses a string that is not an ISO date', () => {
    expect(() => dayBefore('2024-1-1')).toThrow(RangeError)
  })
})

describe('formatWindow', () => {
  it('turns the end-exclusive contract window into an inclusive range for readers', () => {
    expect(formatWindow({ start: '2015-01-01', end_exclusive: '2024-01-01' })).toBe('2015-01-01 to 2023-12-31')
    expect(formatWindow({ start: '2024-01-01', end_exclusive: '2026-10-01' })).toBe('2024-01-01 to 2026-09-30')
  })
})

describe('statusLabel', () => {
  it('capitalises each milestone status', () => {
    expect([statusLabel('done'), statusLabel('current'), statusLabel('planned')]).toEqual(['Done', 'Current', 'Planned'])
  })
})

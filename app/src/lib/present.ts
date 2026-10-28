/**
 * Pure presentation transforms for values that arrive through the JSON contract.
 * Nothing here computes a result of the study; it only reshapes strings for display.
 */
import type { DateWindow, MilestoneStatus } from './contract'

/** `<40 or 64 hex>` -> first 7 hex; `<40 or 64 hex>-dirty` keeps its suffix; `uncommitted` is unchanged. */
export function shortCommit(commit: string): string {
  const m = /^([0-9a-f]{40}|[0-9a-f]{64})(-dirty)?$/.exec(commit)
  if (m === null) return commit
  return `${m[1].slice(0, 7)}${m[2] ?? ''}`
}

/** The calendar day before an ISO date (`2024-01-01` -> `2023-12-31`), leap years included. */
export function dayBefore(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate)
  if (m === null) throw new RangeError(`not an ISO date: ${isoDate}`)
  // Not Date.UTC: it reads the years 0-99 as 1900-1999, and the contract accepts those years.
  const t = new Date(0)
  t.setUTCFullYear(Number(m[1]), Number(m[2]) - 1, Number(m[3]) - 1)
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${pad(t.getUTCFullYear(), 4)}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}`
}

/** `[2015-01-01, 2024-01-01)` -> `2015-01-01 to 2023-12-31`: the contract is end-exclusive, readers think inclusive. */
export function formatWindow(w: DateWindow): string {
  return `${w.start} to ${dayBefore(w.end_exclusive)}`
}

const STATUS_LABELS: Record<MilestoneStatus, string> = { done: 'Done', current: 'Current', planned: 'Planned' }

export function statusLabel(status: MilestoneStatus): string {
  return STATUS_LABELS[status]
}

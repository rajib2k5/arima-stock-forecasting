/**
 * A p-value as fitText.pParts sets it: three decimals from 0.001, a power of ten in a superscript
 * below it, "< 1e-300" for one that underflowed, never a bare 0 or "e-" text. One component for the
 * stationarity, fit and forecast pages, so the three cannot drift apart. Formatting only.
 */
import { pParts } from './fitText'

export function PValue({ p }: { p: number | null }) {
  const parts = pParts(p)
  if ('text' in parts) return <>{parts.text}</>
  return (
    <>
      {parts.mantissa} × 10<sup>{parts.exponent}</sup>
    </>
  )
}

/** Parsed copies of the hand-written prices and eda fixtures, for view and presentation tests. */
import { parseEda, parsePrices, type Eda, type Prices } from '../../lib/contract.payloads'
import pricesData from './prices.data.json'
import edaData from './eda.data.json'

export function fixturePrices(): Prices {
  const r = parsePrices(structuredClone(pricesData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.prices
}

export function fixtureEda(): Eda {
  const r = parseEda(structuredClone(edaData))
  if (!r.ok) throw new Error(r.errors.join('; '))
  return r.eda
}

export function pricesEnvelope(): unknown {
  return { schema_version: '1.1.0', artifact: 'prices', generated_at: '2026-10-29T12:30:00Z', source_commit: 'b'.repeat(40), data: structuredClone(pricesData) }
}

export function edaEnvelope(): unknown {
  return { schema_version: '1.1.0', artifact: 'eda', generated_at: '2026-10-29T12:30:00Z', source_commit: 'b'.repeat(40), data: structuredClone(edaData) }
}

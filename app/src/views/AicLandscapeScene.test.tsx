/**
 * The landscape scene in jsdom, with react-three-fiber and drei replaced by stand-ins that record
 * what the scene asks them to draw: labels (Text), markers (Sphere, Octahedron) and lines (Line).
 *
 * Two guards. Every label must be a character the bundled Inter font covers, because troika fetches
 * a missing glyph from a CDN (see AicAxesScene.test.tsx); AIC values are negative, so the minus sign
 * must be the ASCII one. And every status must get its own marker, so a failure never looks like a fit.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import AicLandscapeScene from './AicLandscapeScene'
import { fixtureAicGrid } from '../test/fixtures/payloads'
import { FAILED_Y } from '../lib/aicLandscape'

type Drawn = { kind: string; name?: string; text?: string; wireframe?: boolean; color?: string; points?: number; ys?: number[] }
const drawn = vi.hoisted(() => [] as Drawn[])

vi.mock('@react-three/fiber', () => ({ Canvas: ({ children }: { children: ReactNode }) => children }))
vi.mock('@react-three/drei', () => {
  const material = (children: ReactNode) => (children as { props?: { color?: string; wireframe?: boolean } })?.props ?? {}
  return {
    Billboard: ({ children }: { children: ReactNode }) => children,
    OrbitControls: () => null,
    Text: ({ children }: { children: ReactNode }) => {
      drawn.push({ kind: 'text', text: String(children) })
      return null
    },
    Line: ({ name, points }: { name?: string; points: unknown[] }) => {
      drawn.push({ kind: 'line', name, points: points.length, ys: [...new Set((points as number[][]).map((pt) => pt[1]))] })
      return null
    },
    Sphere: ({ name, children }: { name: string; children: ReactNode }) => {
      drawn.push({ kind: 'sphere', name, ...material(children) })
      return null
    },
    Octahedron: ({ name, children }: { name: string; children: ReactNode }) => {
      drawn.push({ kind: 'octahedron', name, ...material(children) })
      return null
    },
  }
})

const MOTION = { autoRotate: false, autoRotateSpeed: 0, enableDamping: false, frameloop: 'demand' as const }

function drawScene(d: number, trends: ('n' | 'c' | 't')[]) {
  // The stand-in Canvas puts r3f's <group> in the DOM, which React reports; that is expected.
  vi.spyOn(console, 'error').mockImplementation(() => {})
  render(<AicLandscapeScene grid={fixtureAicGrid()} d={d} trends={trends} motion={MOTION} />)
  return [...drawn]
}

afterEach(() => {
  drawn.length = 0
  vi.restoreAllMocks()
})

describe('AicLandscapeScene markers', () => {
  it('gives each status of d = 1 its own marker', () => {
    const items = drawScene(1, ['n', 't'])
    const byName = (status: string) => items.filter((x) => x.name?.includes(status))
    // ok: solid spheres; the chosen one is a sphere marked "chosen"
    const ok = byName(' ok')
    expect(ok.every((x) => x.kind === 'sphere' && !x.wireframe)).toBe(true)
    expect(ok.filter((x) => x.name?.endsWith('chosen')).map((x) => x.name)).toEqual(['cell d1 p0 q1 t ok chosen'])
    // not converged: a hollow (wireframe) sphere
    expect(byName('not_converged')).toEqual([expect.objectContaining({ kind: 'sphere', wireframe: true, name: 'cell d1 p1 q0 n not_converged' })])
    // failed: a cross below the floor (the floor is where the lowest AIC sits), a line of 4 points
    expect(byName('failed')).toEqual([{ kind: 'line', name: 'cell d1 p1 q1 t failed', points: 4, ys: [FAILED_Y] }])
    expect(FAILED_Y).toBeLessThan(0)
  })

  it('draws near-unit-root cells as octahedra, never as spheres', () => {
    const items = drawScene(2, ['n'])
    const flagged = items.filter((x) => x.name?.includes('near_unit_root'))
    expect(flagged.map((x) => [x.kind, x.name])).toEqual([
      ['octahedron', 'cell d2 p0 q1 n near_unit_root'],
      ['octahedron', 'cell d2 p1 q1 n near_unit_root'],
    ])
    expect(items.some((x) => x.kind === 'sphere' && x.name?.includes('near_unit_root'))).toBe(false)
  })

  it('draws only the cells of the d it is given', () => {
    const items = drawScene(0, ['c'])
    const cells = items.filter((x) => x.name?.startsWith('cell'))
    expect(cells).toHaveLength(4)
    expect(cells.every((x) => x.name?.startsWith('cell d0 '))).toBe(true)
  })
})

describe('AicLandscapeScene labels', () => {
  it('labels the axes and the AIC scale, with an ASCII minus', () => {
    const texts = drawScene(1, ['n', 't']).filter((x) => x.kind === 'text').map((x) => x.text)
    expect(texts).toEqual(expect.arrayContaining(['p', 'q', 'AIC', '0', '5', '-1796', '-1790']))
  })

  it('uses only Basic Latin, so the bundled font covers every label', () => {
    for (const d of [0, 1, 2]) {
      const texts = drawScene(d, d === 1 ? ['n', 't'] : d === 0 ? ['c'] : ['n']).filter((x) => x.kind === 'text').map((x) => x.text ?? '')
      expect(texts.length).toBeGreaterThan(0)
      for (const text of texts) for (const ch of text) expect(ch.codePointAt(0), `"${text}" has U+${ch.codePointAt(0)?.toString(16)}`).toBeLessThanOrEqual(0x7e)
      drawn.length = 0
    }
  })
})

/**
 * The 3D scene draws its labels with troika-three-text, which resolves glyphs through the font we
 * bundle (Inter, latin subset). For a character that font lacks, troika's fallback fetches a
 * replacement font from cdn.jsdelivr.net at run time, and `unicodeFontsURL` cannot close that
 * path (if the URL fails, troika retries on the CDN). So the guard is here: every label the scene
 * draws must be a character the bundled font covers. A future "φ" or "Δ" label fails this file.
 *
 * jsdom has no WebGL, so `Canvas` and drei are replaced by stand-ins that keep only what the
 * scene hands to `Text`: the string and the font file.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { inflateSync } from 'node:zlib'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { buildAxes } from '../lib/aicAxes'
import AicAxesScene from './AicAxesScene'

const drawn = vi.hoisted(() => [] as { text: string; font: string }[])

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: { children: ReactNode }) => children,
}))
vi.mock('@react-three/drei', () => ({
  Billboard: ({ children }: { children: ReactNode }) => children,
  Line: () => null,
  OrbitControls: () => null,
  Text: ({ children, font }: { children: ReactNode; font: string }) => {
    drawn.push({ text: String(children), font })
    return null
  },
}))

// The font file the scene loads, read from disk: the `?url` import in the scene only gives a URL.
const FONT_FILE = 'inter-latin-400-normal.woff'
const FONT_PATH = resolve(import.meta.dirname, '../../node_modules/@fontsource/inter/files', FONT_FILE)

/**
 * The code points the WOFF font has a glyph for, from its 'cmap' table (format 4, the Basic
 * Multilingual Plane, which is all a label needs). WOFF stores each table zlib-compressed unless
 * that would not make it smaller. All numbers in the file are big-endian, which is what DataView
 * reads by default.
 */
function coveredCodePoints(woff: Uint8Array): (codePoint: number) => boolean {
  const viewOf = (bytes: Uint8Array) => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const file = viewOf(woff)
  let table: DataView | undefined
  for (let i = 0; i < file.getUint16(12); i++) {
    const entry = 44 + i * 20 // 44-byte header, then 20 bytes per table: tag, offset, compLength, origLength, checksum
    if (String.fromCharCode(...woff.subarray(entry, entry + 4)) !== 'cmap') continue
    const compressed = file.getUint32(entry + 8)
    const original = file.getUint32(entry + 12)
    const offset = file.getUint32(entry + 4)
    const bytes = woff.subarray(offset, offset + compressed)
    table = viewOf(compressed < original ? inflateSync(bytes) : bytes)
  }
  if (!table) throw new Error('the font has no cmap table')
  const cmap = table
  let sub: number | undefined // the Windows Unicode BMP subtable: platform 3, encoding 1
  for (let i = 0; i < cmap.getUint16(2); i++) {
    const record = 4 + i * 8
    if (cmap.getUint16(record) === 3 && cmap.getUint16(record + 2) === 1) sub = cmap.getUint32(record + 4)
  }
  if (sub === undefined || cmap.getUint16(sub) !== 4) throw new Error('expected a format 4 (3, 1) cmap subtable')
  const segments = cmap.getUint16(sub + 6) / 2
  const ends = sub + 14
  const starts = ends + segments * 2 + 2 // skips the 2-byte reserved pad
  const deltas = starts + segments * 2
  const rangeOffsets = deltas + segments * 2
  return (codePoint) => {
    if (codePoint > 0xffff) return false
    for (let i = 0; i < segments; i++) {
      if (cmap.getUint16(ends + i * 2) < codePoint) continue
      const start = cmap.getUint16(starts + i * 2)
      if (start > codePoint) return false
      const delta = cmap.getUint16(deltas + i * 2)
      const rangeOffset = cmap.getUint16(rangeOffsets + i * 2)
      if (rangeOffset === 0) return ((codePoint + delta) & 0xffff) !== 0
      return cmap.getUint16(rangeOffsets + i * 2 + rangeOffset + 2 * (codePoint - start)) !== 0
    }
    return false
  }
}

const hasGlyph = coveredCodePoints(readFileSync(FONT_PATH))

afterEach(() => {
  drawn.length = 0
  vi.restoreAllMocks()
})

/** Renders the scene once and returns what it asked `Text` to draw. */
function labelsDrawn() {
  // The stand-in Canvas puts react-three-fiber's <group> in the DOM, which React reports as an
  // unrecognised tag. That is the only complaint expected.
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  render(<AicAxesScene motion={{ autoRotate: false, autoRotateSpeed: 0, enableDamping: false, frameloop: 'demand' }} />)
  for (const [message, tag] of errors.mock.calls) expect(`${message} ${tag}`).toMatch(/unrecognized in this browser.*group/)
  return [...drawn]
}

describe('the font coverage reader', () => {
  it('finds the characters the labels use and rejects the ones the font lacks', () => {
    for (const ok of ['0', '5', 'p', 'q', 'A', 'I', 'C', ' ']) expect(hasGlyph(ok.codePointAt(0)!)).toBe(true)
    // phi, capital delta, an arrow outside the subset, and a CJK character
    for (const missing of ['φ', 'Δ', '→', '中']) expect(hasGlyph(missing.codePointAt(0)!)).toBe(false)
  })
})

describe('AicAxesScene labels', () => {
  it('draws exactly the axis titles and tick labels that buildAxes specifies', () => {
    const expected = buildAxes().flatMap((axis) => [axis.title, ...axis.ticks.map((t) => t.label)])
    // 3 titles (p, q, AIC) + 6 ticks on p + 6 ticks on q = 15; the AIC axis has no ticks
    expect(expected).toHaveLength(15)
    expect(labelsDrawn().map((l) => l.text)).toEqual(expected)
  })

  it('loads every label with the bundled Inter font file', () => {
    const labels = labelsDrawn()
    expect(labels.length).toBeGreaterThan(0)
    for (const { font } of labels) expect(font).toMatch(new RegExp(`${FONT_FILE.replace('.', '\\.')}$`))
  })

  it('uses only Basic Latin, so troika never needs its CDN fallback', () => {
    const labels = labelsDrawn().map((l) => l.text)
    expect(labels.length).toBeGreaterThan(0)
    for (const text of labels) {
      for (const char of text) {
        const code = char.codePointAt(0)!
        expect(code, `"${text}" contains U+${code.toString(16).toUpperCase().padStart(4, '0')}, outside Basic Latin`).toBeGreaterThanOrEqual(0x20)
        expect(code, `"${text}" contains U+${code.toString(16).toUpperCase().padStart(4, '0')}, outside Basic Latin`).toBeLessThanOrEqual(0x7e)
      }
    }
  })

  it('draws only characters that the bundled font file really has a glyph for', () => {
    for (const { text } of labelsDrawn()) {
      for (const char of text) {
        expect(hasGlyph(char.codePointAt(0)!), `the bundled font has no glyph for "${char}" in the label "${text}"`).toBe(true)
      }
    }
  })
})

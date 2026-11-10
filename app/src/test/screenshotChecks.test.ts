/**
 * The screenshot tool's checks (tools/screenshots/checks.mjs), tested here so that `npm run verify`
 * runs them. Each rule is flipped on its own against a page that passes every other rule.
 */
import { describe, expect, it } from 'vitest'
import { BLANK_SHARE, BOUNDARY_TEXTS, dominantShare, fileName, isBlank, labelPattern, problems, walkDay, type PageFacts, type ShotNeeds } from '../../../tools/screenshots/checks.mjs'

/** RGBA bytes for `n` pixels: all one colour except `odd` of them. */
function pixels(n: number, odd = 0): Uint8Array {
  const rgba = new Uint8Array(n * 4)
  for (let i = 0; i < n; i++) rgba.set(i < odd ? [224, 164, 88, 255] : [33, 40, 54, 255], i * 4)
  return rgba
}

const drawn = { width: 100, height: 100, rgba: pixels(10_000, 300) }

/** A page that passes every check of a 3D shot and of the walk-forward shot. */
function clean(): PageFacts {
  return {
    theme: 'dark',
    headings: ['Forecast and evaluation', 'Walk forward, one day at a time'],
    alerts: [],
    statuses: [],
    text: 'Forecast and evaluation\nDay 114 of 227',
    pageErrors: [],
    canvas: drawn,
    walk: { status: 'Day 114 of 227, 2023-07-20. Forecast made the evening before: median $192.32.', button: 'Play' },
    selected: { Model: ['Course refit'], Method: ["Static multi-step (the course's)"], Window: ['Test, 2023-02-06 to 2023-12-29'] },
  }
}
const needs: ShotNeeds = { theme: 'dark', heading: 'Forecast and evaluation', canvas: true, walk: true }
const picked: ShotNeeds = { theme: 'dark', heading: 'Forecast and evaluation', selected: { Model: 'Course refit', Method: "Static multi-step (the course's)", Window: 'Test' } }

describe('fileName', () => {
  it('names a shot m5-<section>[-<suffix>]-<theme>.png', () => {
    expect(fileName('about', 'dark')).toBe('m5-about-dark.png')
    expect(fileName('landscape', 'light', '3d')).toBe('m5-landscape-3d-light.png')
    expect(fileName('forecast', 'light', 'walkforward')).toBe('m5-forecast-walkforward-light.png')
    expect(fileName('fit', 'dark', 'mobile')).toBe('m5-fit-mobile-dark.png')
  })

  it('refuses a theme other than light or dark, and a section or suffix that is not lower-case words', () => {
    expect(() => fileName('about', 'sepia')).toThrow(/theme must be light or dark/)
    expect(() => fileName('About', 'dark')).toThrow(/section must be/)
    expect(() => fileName('about page', 'dark')).toThrow(/section must be/)
    expect(() => fileName('about', 'dark', '3D')).toThrow(/suffix must be/)
    expect(() => fileName('about', 'dark', '-x')).toThrow(/suffix must be/)
  })
})

describe('blank canvas', () => {
  it('measures the share of the most common colour, alpha included', () => {
    expect(dominantShare(pixels(10_000))).toBe(1)
    expect(dominantShare(pixels(10_000, 97))).toBeCloseTo(0.9903, 10)
    const half = pixels(4)
    half.set([33, 40, 54, 0], 0) // the same colour, transparent: a different pixel
    half.set([33, 40, 54, 0], 4)
    expect(dominantShare(half)).toBe(0.5)
    expect(dominantShare(new Uint8Array(0))).toBe(1)
  })

  it('calls a canvas blank from 99.9% of its pixels in one colour, and not below', () => {
    expect(BLANK_SHARE).toBe(0.999)
    expect(isBlank(pixels(10_000))).toBe(true)
    expect(isBlank(pixels(10_000, 10))).toBe(true) // exactly 99.9%
    expect(isBlank(pixels(10_000, 11))).toBe(false) // 99.89%
    // The sparsest real scene, the empty axes, measured 99.03%.
    expect(isBlank(pixels(10_000, 97))).toBe(false)
  })
})

describe('walkDay', () => {
  it('reads the day and the window length from the status line', () => {
    expect(walkDay('Day 114 of 227, 2023-07-20.')).toEqual({ day: 114, of: 227 })
    expect(walkDay('Loading')).toBeNull()
    expect(walkDay(null)).toBeNull()
  })
})

describe('labelPattern', () => {
  it('matches a control by its whole label, or by its label and a comma-separated tail', () => {
    expect(labelPattern('Course refit').test('Course refit')).toBe(true)
    expect(labelPattern('Test').test('Test, 2023-02-06 to 2023-12-29')).toBe(true)
    expect(labelPattern('Out of sample').test('Out of sample, 2024-01-02 to 2026-09-30')).toBe(true)
  })
  it('takes the label literally, brackets and apostrophes included, and matches no longer or shorter label', () => {
    expect(labelPattern("Static multi-step (the course's)").test("Static multi-step (the course's)")).toBe(true)
    expect(labelPattern('AIC choice (ADR-0002)').test('AIC choice ADR-0002')).toBe(false)
    expect(labelPattern('Walk-forward one-step').test('Walk-forward one-step, refit every 21 days')).toBe(true)
    expect(labelPattern('Walk-forward one-step').test('Walk-forward one-step refit')).toBe(false)
    expect(labelPattern('Test').test('Testing')).toBe(false)
    expect(labelPattern('Test').test('A Test')).toBe(false)
    expect(labelPattern('Course').test('Course refit')).toBe(false)
  })
})

describe('problems', () => {
  it('finds nothing wrong with a page that is ready', () => {
    expect(problems(clean(), needs)).toEqual([])
    // A shot that needs no canvas and no walk ignores both.
    expect(problems({ ...clean(), canvas: null, walk: null }, { theme: 'dark', heading: 'Forecast and evaluation' })).toEqual([])
  })

  it('refuses a page in the other theme', () => {
    expect(problems({ ...clean(), theme: 'light' }, needs)).toEqual(['the page is in the light theme, not dark'])
    expect(problems({ ...clean(), theme: null }, needs)).toEqual(['the page is in the unset theme, not dark'])
  })

  it('refuses a page without its section heading', () => {
    expect(problems({ ...clean(), headings: ['About'] }, needs)).toEqual(['the section heading "Forecast and evaluation" is missing'])
    expect(problems({ ...clean(), headings: [' Forecast and evaluation '] }, needs)).toEqual([])
  })

  it('refuses a page that shows an error', () => {
    expect(problems({ ...clean(), alerts: ['Could not load evaluation.json.'] }, needs)).toEqual(['an error is shown (role="alert"): Could not load evaluation.json.'])
  })

  it('refuses a page that is still loading', () => {
    expect(problems({ ...clean(), statuses: ['Loading data/evaluation.json…'] }, needs)).toEqual(['still loading (role="status"): Loading data/evaluation.json…'])
  })

  it('refuses a page that shows a 3D fallback in place of the scene', () => {
    for (const text of BOUNDARY_TEXTS) {
      expect(problems({ ...clean(), text: `AIC landscape\n${text}, so the table below has every cell.` }, needs)).toEqual([`the 3D fallback is shown: "${text}"`])
    }
  })

  it('refuses a page that threw', () => {
    expect(problems({ ...clean(), pageErrors: ['TypeError: x is undefined'] }, needs)).toEqual(['the page threw: TypeError: x is undefined'])
  })

  it('refuses a 3D shot whose canvas is blank, missing, or out of view', () => {
    expect(problems({ ...clean(), canvas: { width: 100, height: 100, rgba: pixels(10_000) } }, needs)).toEqual(['the 3D canvas is blank: 100.00% of its 100 x 100 pixels are one colour'])
    expect(problems({ ...clean(), canvas: null }, needs)).toEqual(['the 3D canvas is missing or has no visible pixels'])
    expect(problems({ ...clean(), canvas: { width: 0, height: 0, rgba: new Uint8Array(0) } }, needs)).toEqual(['the 3D canvas is missing or has no visible pixels'])
    // The same blank canvas is not judged on a shot that needs none.
    expect(problems({ ...clean(), canvas: { width: 100, height: 100, rgba: pixels(10_000) } }, { ...needs, canvas: false })).toEqual([])
  })

  it('refuses a shot whose controls are not set to the named choices', () => {
    expect(problems(clean(), picked)).toEqual([])
    const sel = (selected: Record<string, string[]>) => problems({ ...clean(), selected: { ...clean().selected, ...selected } }, picked)
    expect(sel({ Model: ['AIC choice (ADR-0002)'] })).toEqual(['the "Model" control is set to "AIC choice (ADR-0002)", not "Course refit"'])
    expect(sel({ Window: ['Out of sample, 2024-01-02 to 2026-09-30'] })).toEqual(['the "Window" control is set to "Out of sample, 2024-01-02 to 2026-09-30", not "Test"'])
    expect(sel({ Method: [] })).toEqual(['the "Method" control has 0 choices selected, not one'])
    expect(sel({ Method: ["Static multi-step (the course's)", 'Walk-forward one-step'] })).toEqual(['the "Method" control has 2 choices selected, not one'])
    expect(problems({ ...clean(), selected: {} }, picked)).toEqual(['the "Model" control is missing', 'the "Method" control is missing', 'the "Window" control is missing'])
    // A shot that names no choices does not look at the controls.
    expect(problems({ ...clean(), selected: {} }, needs)).toEqual([])
  })

  it('refuses a walk-forward shot that is not paused about half way', () => {
    const at = (day: number, button = 'Play') => problems({ ...clean(), walk: { status: `Day ${day} of 200, 2023-07-20.`, button } }, needs)
    expect(at(80)).toEqual([]) // 0.40
    expect(at(120)).toEqual([]) // 0.60
    expect(at(79)).toEqual(['the walk-forward is at day 79 of 200, not about half way'])
    expect(at(121)).toEqual(['the walk-forward is at day 121 of 200, not about half way'])
    expect(at(100, 'Pause')).toEqual(['the walk-forward is not paused: its button reads "Pause"'])
    expect(problems({ ...clean(), walk: null }, needs)).toEqual(['the walk-forward status line is missing', 'the walk-forward is not paused: its button reads "nothing"'])
  })
})

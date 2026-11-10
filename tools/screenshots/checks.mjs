/**
 * The screenshot tool's decisions, as pure functions with no dependencies: what a shot is called,
 * and whether the page in front of the camera is fit to be captured. shoot.mjs gathers the facts in
 * the browser; this module judges them, so app/src/test/screenshotChecks.test.ts can test every
 * rule without a browser.
 */

/** The milestone the images belong to: every file is docs/images/m5-<section>-<theme>.png. */
export const PREFIX = 'm5'
export const THEMES = ['light', 'dark']

/**
 * The file name of a shot: m5-<section>[-<suffix>]-<theme>.png, e.g. m5-about-dark.png,
 * m5-landscape-3d-light.png, m5-fit-mobile-light.png. Sections and suffixes are lower-case words
 * joined by hyphens.
 */
export function fileName(section, theme, suffix = '') {
  const word = /^[a-z0-9]+(-[a-z0-9]+)*$/
  if (!word.test(section)) throw new Error(`section must be lower-case words joined by hyphens, got ${JSON.stringify(section)}`)
  if (suffix !== '' && !word.test(suffix)) throw new Error(`suffix must be lower-case words joined by hyphens, got ${JSON.stringify(suffix)}`)
  if (!THEMES.includes(theme)) throw new Error(`theme must be light or dark, got ${JSON.stringify(theme)}`)
  return `${PREFIX}-${section}${suffix ? `-${suffix}` : ''}-${theme}.png`
}

/** Text the app shows instead of a 3D view: SceneBoundary's fallbacks and the no-WebGL notes. */
export const BOUNDARY_TEXTS = ['3D preview unavailable', 'The 3D view could not start in this browser', 'cannot create a WebGL2 context']

/**
 * A canvas counts as blank when at least this share of its pixels have one colour. A WebGL canvas
 * that drew nothing is exactly one colour (its clear colour, or the card behind it); the share
 * leaves room for a few stray pixels (0.1%). Measured on 2026-10-30 at 1440 x 900: the sparsest real
 * scene, the Architecture page's empty axes, has 99.03% of its pixels in one colour (0.97% drawn,
 * about ten times the allowance); the AIC landscape 96.4%.
 */
export const BLANK_SHARE = 0.999

/**
 * The share of pixels that have the most common colour, from RGBA bytes (4 per pixel). Measured on
 * the captured screenshot's pixels, never on canvas.toDataURL, which reads back empty for WebGL.
 * An image with no pixels has share 1: nothing is drawn.
 */
export function dominantShare(rgba) {
  const n = Math.floor(rgba.length / 4)
  if (n === 0) return 1
  const counts = new Map()
  let best = 0
  for (let i = 0; i < n * 4; i += 4) {
    const key = ((rgba[i] << 24) | (rgba[i + 1] << 16) | (rgba[i + 2] << 8) | rgba[i + 3]) >>> 0
    const c = (counts.get(key) ?? 0) + 1
    counts.set(key, c)
    if (c > best) best = c
  }
  return best / n
}

export function isBlank(rgba, share = BLANK_SHARE) {
  return dominantShare(rgba) >= share
}

/** The walk-forward shot shows the animation paused about half way: day k of n, k / n in this range. */
export const WALK_MIDDLE = [0.4, 0.6]

/** "Day 113 of 226, 2023-…" as { day, of }, or null if the status says something else. */
export function walkDay(status) {
  const m = /Day (\d+) of (\d+)/.exec(status ?? '')
  return m ? { day: Number(m[1]), of: Number(m[2]) } : null
}

/**
 * The visible label of a control, as a pattern: the label itself, or the label followed by ", " and
 * more (the forecast page's window buttons read "Test, 2023-02-06 to 2023-12-29"). The tool picks a
 * control by this pattern and checks the picked one by it, so the two cannot disagree.
 */
export function labelPattern(label) {
  return new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(, .*)?$`)
}

/**
 * Everything wrong with the page for this shot, as sentences; empty when it can be captured.
 * `page` holds what shoot.mjs read in the browser:
 * - theme: the html element's data-theme; headings: the text of every h2 on the page;
 * - alerts: the text of every role="alert" element; statuses: of every role="status" element;
 * - text: the page's visible text; pageErrors: uncaught errors since it loaded;
 * - canvas (3D shots): { width, height, rgba } cropped from the captured image, or null if absent;
 * - walk (the walk-forward shot): { status, button }, the status line and the play button's label;
 * - selected: for each labelled radio group, the text of every radio in it that is checked.
 * `expect` says what this shot needs: { theme, heading, canvas?: boolean, walk?: boolean,
 * selected?: { <group label>: <control label> } }.
 */
export function problems(page, expect) {
  const out = []
  if (page.theme !== expect.theme) out.push(`the page is in the ${page.theme ?? 'unset'} theme, not ${expect.theme}`)
  if (!(page.headings ?? []).some((h) => h.trim() === expect.heading)) out.push(`the section heading "${expect.heading}" is missing`)
  for (const alert of page.alerts ?? []) out.push(`an error is shown (role="alert"): ${alert.trim().slice(0, 160)}`)
  for (const status of page.statuses ?? []) out.push(`still loading (role="status"): ${status.trim().slice(0, 160)}`)
  for (const text of BOUNDARY_TEXTS) if ((page.text ?? '').includes(text)) out.push(`the 3D fallback is shown: "${text}"`)
  for (const error of page.pageErrors ?? []) out.push(`the page threw: ${String(error).slice(0, 160)}`)
  if (expect.canvas) {
    const c = page.canvas
    if (!c || c.width === 0 || c.height === 0) out.push('the 3D canvas is missing or has no visible pixels')
    else if (isBlank(c.rgba)) out.push(`the 3D canvas is blank: ${(dominantShare(c.rgba) * 100).toFixed(2)}% of its ${c.width} x ${c.height} pixels are one colour`)
  }
  if (expect.walk) {
    const at = walkDay(page.walk?.status)
    if (!at) out.push('the walk-forward status line is missing')
    else if (at.day / at.of < WALK_MIDDLE[0] || at.day / at.of > WALK_MIDDLE[1]) out.push(`the walk-forward is at day ${at.day} of ${at.of}, not about half way`)
    if (page.walk?.button !== 'Play') out.push(`the walk-forward is not paused: its button reads "${page.walk?.button ?? 'nothing'}"`)
  }
  for (const [group, label] of Object.entries(expect.selected ?? {})) {
    const checked = page.selected?.[group]
    if (!checked) out.push(`the "${group}" control is missing`)
    else if (checked.length !== 1) out.push(`the "${group}" control has ${checked.length} choices selected, not one`)
    else if (!labelPattern(label).test(checked[0].trim())) out.push(`the "${group}" control is set to "${checked[0].trim()}", not "${label}"`)
  }
  return out
}

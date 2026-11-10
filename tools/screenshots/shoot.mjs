/**
 * Screenshots of the built app for the docs, checked before each capture.
 *
 *   cd app && npm run build && npm run screenshots
 *
 * Serves app/dist on a port the OS picks (serve.mjs), opens it in Playwright's cached headless
 * Chromium (WebGL through SwiftShader; no browser is ever downloaded), and writes viewport-sized
 * PNGs (two cropped to one card) to docs/images/. Before each capture the page is checked
 * (checks.mjs): an error shown (role="alert"), a loading message (role="status"), a 3D fallback text,
 * an uncaught error, a blank 3D canvas (measured on the captured pixels), the wrong theme, a missing
 * section heading or a control not set to the choice the shot names stops that shot; the tool then
 * exits 1 naming every failed shot, and writes none of them.
 *
 * Names: m5-<section>[-<suffix>]-<theme>.png, theme light or dark.
 *   Desktop (1440 x 900), both themes: about, explorer, stationarity, landscape, landscape-3d, fit,
 *   forecast, forecast-walkforward (the walk-forward animation paused about half way), architecture,
 *   architecture-3d.
 *   Desktop, light only, cropped to the "Forecast in dollars" card (chart and legend):
 *   forecast-fan-course-static (Course refit, static, test window) and
 *   forecast-fan-aic-static (AIC choice, static, out-of-sample window). Their controls are picked
 *   by visible label (checks.labelPattern), and the checks confirm each one is selected.
 *   Mobile (375 x 812, mobile emulation, scale 2), suffix "mobile": about, explorer, stationarity,
 *   fit and forecast in light; about, fit and forecast in dark. The chart pages are scrolled to a
 *   chart, so the axis text can be read.
 *
 * Options: --only <text> takes only the shots whose file name contains the text; --out <dir> writes
 * somewhere other than docs/images.
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { dominantShare, fileName, labelPattern, problems } from './checks.mjs'
import { serve } from './serve.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..', '..')
// Playwright is a devDependency of app/: resolve it from there, not from this folder.
const { chromium } = createRequire(join(REPO, 'app', 'package.json'))('playwright')

const args = process.argv.slice(2)
const option = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined)
const OUT = resolve(option('--out') ?? join(REPO, 'docs', 'images'))
const ONLY = option('--only')
const DIST = join(REPO, 'app', 'dist')
const THEME_KEY = 'arima:arima-stock-forecasting:theme'
const WAIT_MS = 30_000

const DESKTOP = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }
const STATIC = "Static multi-step (the course's)"
const CLIP_MARGIN = 12
/** The "Forecast in dollars" card: the fan chart, its legend and its note. */
const fanCard = (page) => page.locator('.card').filter({ has: page.getByTestId('fan-chart') })
const MOBILE = { viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }

/** Each shot: the route, the heading it must show, what to do before the capture, and what to check. */
const SECTIONS = [
  { section: 'about', route: 'about', heading: 'About' },
  { section: 'explorer', route: 'explorer', heading: 'Price explorer' },
  { section: 'stationarity', route: 'stationarity', heading: 'Stationarity and identification' },
  { section: 'landscape', route: 'landscape', heading: 'AIC landscape' },
  { section: 'landscape', suffix: '3d', route: 'landscape', heading: 'AIC landscape', canvas: true, prepare: (page) => scrollTo(page, '.aic-canvas', 'center', true) },
  { section: 'fit', route: 'fit', heading: 'Fit and diagnostics' },
  { section: 'forecast', route: 'forecast', heading: 'Forecast and evaluation' },
  { section: 'forecast', suffix: 'walkforward', route: 'forecast', heading: 'Forecast and evaluation', walk: true, prepare: walkHalfway },
  { section: 'forecast', suffix: 'fan-course-static', route: 'forecast', heading: 'Forecast and evaluation', themes: ['light'], clip: fanCard, selected: { Model: 'Course refit', Method: STATIC, Window: 'Test' } },
  { section: 'forecast', suffix: 'fan-aic-static', route: 'forecast', heading: 'Forecast and evaluation', themes: ['light'], clip: fanCard, selected: { Model: 'AIC choice (ADR-0002)', Method: STATIC, Window: 'Out of sample' } },
  // The layer diagram fades its rows in over about 1.2 s.
  { section: 'architecture', route: 'architecture', heading: 'Architecture', settleMs: 2000 },
  { section: 'architecture', suffix: '3d', route: 'architecture', heading: 'Architecture', canvas: true, prepare: (page) => scrollTo(page, '.aic-canvas', 'center', true) },
]

const MOBILE_SECTIONS = [
  { section: 'about', route: 'about', heading: 'About', themes: ['light', 'dark'] },
  { section: 'explorer', route: 'explorer', heading: 'Price explorer', themes: ['light'], prepare: (page) => scrollTo(page, '.explorer .card', 'start') },
  { section: 'stationarity', route: 'stationarity', heading: 'Stationarity and identification', themes: ['light'], prepare: (page) => scrollToHeading(page, 'ACF and PACF') },
  { section: 'fit', route: 'fit', heading: 'Fit and diagnostics', themes: ['light', 'dark'], prepare: (page) => scrollToHeading(page, 'Residual plots') },
  { section: 'forecast', route: 'forecast', heading: 'Forecast and evaluation', themes: ['light', 'dark'], prepare: (page) => scrollToHeading(page, 'Forecast in dollars') },
]

function plan() {
  const shots = []
  for (const theme of ['light', 'dark']) {
    for (const s of SECTIONS) if (!s.themes || s.themes.includes(theme)) shots.push({ ...s, theme, device: DESKTOP, name: fileName(s.section, theme, s.suffix) })
    for (const s of MOBILE_SECTIONS) if (s.themes.includes(theme)) shots.push({ ...s, theme, device: MOBILE, name: fileName(s.section, theme, 'mobile') })
  }
  return shots.filter((s) => !ONLY || s.name.includes(ONLY))
}

/** Scrolls the first match into view. An `optional` one that never appears is left for the checks to report (a 3D view that fell back, say). */
async function scrollTo(page, selector, block, optional = false) {
  const found = page.locator(selector).first().waitFor({ timeout: WAIT_MS })
  await (optional ? found.catch(() => {}) : found)
  await page.evaluate(([sel, b]) => document.querySelector(sel)?.scrollIntoView({ block: b }), [selector, block])
}

async function scrollToHeading(page, text) {
  const heading = page.getByRole('heading', { name: text, exact: true })
  await heading.waitFor({ timeout: WAIT_MS })
  await heading.evaluate((el) => el.scrollIntoView({ block: 'start' }))
}

/** Clicks, in each named radio group, the control whose visible label is the one named; the checks then confirm each is the one selected. */
async function pick(page, selected) {
  for (const [group, label] of Object.entries(selected)) {
    await page.getByRole('radiogroup', { name: group, exact: true }).getByRole('radio', { name: labelPattern(label) }).click({ timeout: WAIT_MS })
  }
}

/** The walk-forward method, stepped to the middle of its window with Step forward (so it stays paused), in view. */
async function walkHalfway(page) {
  await page.getByRole('radio', { name: 'Walk-forward one-step', exact: true }).click()
  const status = page.getByTestId('walk-status')
  await status.waitFor({ timeout: WAIT_MS })
  const n = Number(/Day \d+ of (\d+)/.exec(await status.textContent())?.[1] ?? 0)
  const forward = page.getByRole('button', { name: 'Step forward', exact: true })
  for (let day = 1; day < Math.round(n / 2); day++) await forward.click()
  await scrollTo(page, '[data-testid="walk-chart"]', 'center')
}

/** Waits (up to WAIT_MS) for loading messages to go and, for a 3D shot, for a canvas to appear; the checks judge what is left. */
async function settle(page, shot) {
  await page.waitForFunction(() => !document.querySelector('[role="status"]'), null, { timeout: WAIT_MS }).catch(() => {})
  await page.evaluate(() => document.fonts.ready)
  if (shot.canvas) await page.locator('.aic-canvas canvas').first().waitFor({ timeout: WAIT_MS }).catch(() => {})
  // Let the 3D scenes draw a few frames, the charts' widths settle and any entrance animation end.
  await page.waitForTimeout(shot.settleMs ?? (shot.canvas ? 2500 : 400))
}

/**
 * The box to crop a card shot to: the card, scrolled into view, with CLIP_MARGIN px of page around
 * it, so its border and an axis label that runs past it are in the picture. Throws unless exactly
 * one element matches.
 */
async function around(locator) {
  await locator.scrollIntoViewIfNeeded({ timeout: WAIT_MS })
  const box = await locator.boundingBox()
  if (!box) throw new Error('the card to crop to is not visible')
  const { width, height } = DESKTOP.viewport
  const x = Math.max(0, Math.floor(box.x - CLIP_MARGIN))
  const y = Math.max(0, Math.floor(box.y - CLIP_MARGIN))
  return { x, y, width: Math.min(width, Math.ceil(box.x + box.width + CLIP_MARGIN)) - x, height: Math.min(height, Math.ceil(box.y + box.height + CLIP_MARGIN)) - y }
}

/** What checks.problems needs, read from the page. */
function readPage(page) {
  return page.evaluate(() => {
    const texts = (sel) => [...document.querySelectorAll(sel)].map((el) => el.textContent ?? '')
    const walk = document.querySelector('[data-testid="walk-status"]')
    const play = document.querySelector('.walk-controls button')
    return {
      theme: document.documentElement.getAttribute('data-theme'),
      headings: texts('h2'),
      alerts: texts('[role="alert"]'),
      statuses: texts('[role="status"]'),
      text: document.body.innerText,
      walk: walk ? { status: walk.textContent, button: play?.textContent ?? null } : null,
      selected: Object.fromEntries(
        [...document.querySelectorAll('[role="radiogroup"][aria-label]')].map((g) => [g.getAttribute('aria-label'), [...g.querySelectorAll('[role="radio"][aria-checked="true"]')].map((r) => r.textContent ?? '')]),
      ),
    }
  })
}

/** The visible part of the first 3D canvas, in screenshot pixels, inset 2 px from its edges; null if none is in view. */
function canvasBox(page, scale) {
  return page.evaluate((s) => {
    const c = document.querySelector('.aic-canvas canvas')
    if (!c) return null
    const r = c.getBoundingClientRect()
    const x0 = Math.max(r.left, 0) + 2
    const y0 = Math.max(r.top, 0) + 2
    const x1 = Math.min(r.right, innerWidth) - 2
    const y1 = Math.min(r.bottom, innerHeight) - 2
    if (x1 <= x0 || y1 <= y0) return null
    return { x: Math.round(x0 * s), y: Math.round(y0 * s), w: Math.round((x1 - x0) * s), h: Math.round((y1 - y0) * s) }
  }, scale)
}

/** Decodes a PNG and returns the RGBA bytes of one box, using the browser's own decoder on a blank page. */
async function pixels(decoder, png, box) {
  const b64 = await decoder.evaluate(
    async ({ data, box }) => {
      const blob = await (await fetch(`data:image/png;base64,${data}`)).blob()
      const bitmap = await createImageBitmap(blob, box.x, box.y, box.w, box.h)
      const canvas = new OffscreenCanvas(box.w, box.h)
      const ctx = canvas.getContext('2d')
      ctx.drawImage(bitmap, 0, 0)
      const bytes = ctx.getImageData(0, 0, box.w, box.h).data
      let out = ''
      for (let i = 0; i < bytes.length; i += 0x8000) out += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
      return btoa(out)
    },
    { data: png.toString('base64'), box },
  )
  return { width: box.w, height: box.h, rgba: Buffer.from(b64, 'base64') }
}

async function main() {
  const shots = plan()
  if (shots.length === 0) throw new Error(`no shot matches --only ${ONLY}`)
  await mkdir(OUT, { recursive: true })
  const server = await serve(DIST)
  const browser = await chromium.launch({ headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
  const failed = []
  try {
    for (const shot of shots) {
      const context = await browser.newContext({ ...shot.device, colorScheme: shot.theme })
      await context.addInitScript(
        ([key, theme]) => {
          // The app reads its theme from here at start; a blank page has no storage, and needs none.
          try {
            localStorage.setItem(key, theme)
          } catch {
            /* about:blank */
          }
        },
        [THEME_KEY, shot.theme],
      )
      const page = await context.newPage()
      const pageErrors = []
      page.on('pageerror', (e) => pageErrors.push(e.message))
      try {
        await page.goto(`${server.url}#/${shot.route}`)
        await settle(page, shot)
        if (shot.selected) await pick(page, shot.selected)
        if (shot.prepare) await shot.prepare(page)
        await settle(page, shot)
        const png = await page.screenshot({ type: 'png', ...(shot.clip ? { clip: await around(shot.clip(page)) } : {}) })
        const facts = { ...(await readPage(page)), pageErrors }
        if (shot.canvas) {
          const box = await canvasBox(page, shot.device.deviceScaleFactor)
          facts.canvas = box ? await pixels(await context.newPage(), png, box) : null
        }
        const found = problems(facts, { theme: shot.theme, heading: shot.heading, canvas: shot.canvas, walk: shot.walk, selected: shot.selected })
        if (found.length > 0) {
          failed.push(shot.name)
          console.error(`FAILED ${shot.name}:\n  - ${found.join('\n  - ')}`)
        } else {
          await writeFile(join(OUT, shot.name), png)
          const canvas = facts.canvas ? `  (canvas ${facts.canvas.width} x ${facts.canvas.height}, ${(dominantShare(facts.canvas.rgba) * 100).toFixed(2)}% one colour)` : ''
          console.log(`${shot.name}  ${png.length} bytes${canvas}`)
        }
      } catch (e) {
        failed.push(shot.name)
        console.error(`FAILED ${shot.name}: ${e.message}`)
      } finally {
        await context.close()
      }
    }
  } finally {
    await browser.close()
    await server.close()
  }
  if (failed.length > 0) {
    console.error(`${failed.length} of ${shots.length} shots failed their checks: ${failed.join(', ')}`)
    process.exit(1)
  }
  console.log(`${shots.length} shots written to ${OUT}`)
}

await main()

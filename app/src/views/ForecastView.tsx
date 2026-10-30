/**
 * Forecast and evaluation (course modules 9 and 10): each model's forecasts of the test and
 * out-of-sample windows by the static method (the course's), walk-forward one step ahead, and for
 * the primary model walk-forward with the parameters re-estimated every 21 days; every forecast
 * scored against the random walk, with the Diebold–Mariano test and the interval coverage. Draws
 * evaluation.json and the picked forecast_<model>_<method>.json; every number on the page comes from
 * them, and every reading is fixed text keyed by a verdict Python exported (ADR-0001). Nothing here
 * compares a p-value, a rate or a ratio with anything.
 *
 * Loaded lazily from App.tsx, so its code and data are fetched only when the page opens; a forecast
 * file is fetched only when its model and method are picked.
 */
import { useEffect, useState } from 'react'
import { useEvaluationData, useForecastFile, type EvaluationState, type Load } from '../data/useForecastData'
import { prefersReducedMotion } from '../lib/capabilities'
import type { Envelope } from '../lib/contract'
import { artifactName, LEVELS, type CoverageRow, type CoverageVerdict, type DmRow, type DmVerdict, type Evaluation, type Forecast, type ForecastRow, type ForecastWindow, type Kind, type Method, type ModelId, type WindowId } from '../lib/contract.forecast'
import { pParts, sig } from '../lib/fitText'
import { fmt, pct } from '../lib/format'
import {
  backTransformSentence,
  COVERAGE_LABELS,
  COVERAGE_READINGS,
  days,
  DISTRIBUTION_LABELS,
  DM_LABELS,
  DM_READINGS,
  DM_STATIC_NOTE,
  frameMs,
  insideText,
  LOSS_LABELS,
  METHOD_DESCRIPTIONS,
  usd,
  WINDOW_DESCRIPTIONS,
  WINDOW_LABELS,
} from '../lib/forecastText'
import { describeLoadError, type ArtifactLoadError } from '../lib/loadError'
import { extent, formatLogTick, formatTick, linearScale, logTicks, niceStep, niceTicks } from '../lib/plot'
import { shortCommit } from '../lib/present'
import { useReducedMotion } from './hooks'

const MAX_ERRORS_SHOWN = 12
/**
 * Sizes set on the elements themselves, as on the fit page: `.plot svg` is 100% wide, and a legend
 * icon without its own width and height drew at 300 px in a browser (jsdom cannot see that).
 */
const LEGEND_MARK = { width: 12, height: 12 } as const
/** The drawing's own units: the SVG scales to its card through its viewBox. */
const CHART = { width: 720, height: 300 } as const
const PAD = { l: 58, r: 14, t: 26, b: 26 }

/** A p-value as fitText.pParts sets it: a power of ten in a superscript, never a bare 0. */
function PValue({ p }: { p: number | null }) {
  const parts = pParts(p)
  if ('text' in parts) return <>{parts.text}</>
  return (
    <>
      {parts.mantissa} × 10<sup>{parts.exponent}</sup>
    </>
  )
}

export default function ForecastView() {
  return <ForecastPage state={useEvaluationData()} />
}

/**
 * The page for a given load state of evaluation.json; split from the default export so tests can
 * pass any state. `load` fetches the forecast files and `readReducedMotion` reads the reader's
 * motion preference (tests pass fakes of both).
 */
export function ForecastPage({ state, load, readReducedMotion = prefersReducedMotion }: { state: EvaluationState; load?: Load; readReducedMotion?: () => boolean }) {
  return (
    <section className="forecast">
      <h2>Forecast and evaluation</h2>
      <p className="sub">
        Each model forecasts the test window and the out-of-sample window three ways: one static path from the day before (what the course does),
        one step ahead each evening, and, for the primary model, one step ahead with the parameters estimated again every 21 days. Every forecast is
        scored against the random walk, which forecasts the last price it saw.
      </p>
      <Body state={state} load={load} readReducedMotion={readReducedMotion} />
    </section>
  )
}

function LoadFailure({ artifact, error }: { artifact: string; error: ArtifactLoadError }) {
  const lines = describeLoadError(error)
  return (
    <div className="card callout error" role="alert">
      <strong>Could not load {artifact}.json.</strong>
      <ul>
        {lines.slice(0, MAX_ERRORS_SHOWN).map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
      {lines.length > MAX_ERRORS_SHOWN && <p>…and {lines.length - MAX_ERRORS_SHOWN} more.</p>}
      <p>
        Run <code>uv run python tools/export_app_data.py</code> from the repository root, and reload this page.
      </p>
    </div>
  )
}

function Body({ state, load, readReducedMotion }: { state: EvaluationState; load?: Load; readReducedMotion: () => boolean }) {
  if (state.status === 'loading') {
    return (
      <p className="sub" role="status">
        Loading data/evaluation.json…
      </p>
    )
  }
  if (state.status === 'error') return <LoadFailure artifact={state.artifact} error={state.error} />
  return <Ready evaluation={state.evaluation} envelope={state.envelope} load={load} readReducedMotion={readReducedMotion} />
}

/** A labelled group of radio buttons, as on the fit page. */
function Picker<T extends string>({ label, options, value, onPick }: { label: string; options: { id: T; text: string }[]; value: T; onPick: (id: T) => void }) {
  return (
    <div className="controls" role="radiogroup" aria-label={label}>
      <span className="control-label">{label}</span>
      {options.map((o) => (
        <button key={o.id} type="button" role="radio" aria-checked={o.id === value} className={o.id === value ? 'toggle on' : 'toggle'} onClick={() => onPick(o.id)}>
          {o.text}
        </button>
      ))}
    </div>
  )
}

interface Shown {
  model: ModelId
  method: Method
  kind: Kind
  windowId: WindowId
  modelLabel: string
  methodLabel: string
}

function Ready({ evaluation, envelope, load, readReducedMotion }: { evaluation: Evaluation; envelope: Envelope; load?: Load; readReducedMotion: () => boolean }) {
  const [model, setModel] = useState<ModelId>('aic')
  const [windowId, setWindowId] = useState<WindowId>('test')
  const [picked, setPicked] = useState<Method>('static')
  const [showMean, setShowMean] = useState(false)
  const [tBands, setTBands] = useState(false)
  const [logAxis, setLogAxis] = useState(false)
  const reduced = useReducedMotion(readReducedMotion)
  const entry = evaluation.models.find((m) => m.id === model) ?? evaluation.models[0]
  // The refit exists for the primary model only: another model shows the walk-forward in its place.
  const method = entry.methods.includes(picked) ? picked : 'walk_forward'
  const info = evaluation.methods.find((m) => m.id === method) ?? evaluation.methods[0]
  const file = useForecastFile(model, method, load)
  const shown: Shown = { model, method, kind: info.kind, windowId, modelLabel: entry.label, methodLabel: info.label }
  const artifact = artifactName(model, method)
  return (
    <>
      <div className="card">
        <Picker label="Model" options={evaluation.models.map((m) => ({ id: m.id, text: m.label }))} value={model} onPick={setModel} />
        <Picker label="Method" options={entry.methods.map((id) => ({ id, text: evaluation.methods.find((m) => m.id === id)?.label ?? id }))} value={method} onPick={setPicked} />
        <Picker label="Window" options={evaluation.windows.map((w) => ({ id: w.id, text: `${WINDOW_LABELS[w.id]}, ${w.start} to ${w.end}` }))} value={windowId} onPick={setWindowId} />
        <div className="controls toggles">
          <label>
            <input type="checkbox" checked={showMean} onChange={(e) => setShowMean(e.target.checked)} /> Show the mean, exp(μ + s²/2)
          </label>
          <label>
            <input type="checkbox" checked={tBands} onChange={(e) => setTBands(e.target.checked)} /> Student-t bands (variance-matched) instead of normal
          </label>
          <label>
            <input type="checkbox" checked={logAxis} onChange={(e) => setLogAxis(e.target.checked)} /> Log price axis (forecast chart)
          </label>
        </div>
        <p className="sub note">
          {METHOD_DESCRIPTIONS[method]} {WINDOW_DESCRIPTIONS[windowId]}
        </p>
      </div>
      {file.status === 'loading' && (
        <p className="sub" role="status">
          Loading data/{artifact}.json…
        </p>
      )}
      {file.status === 'error' && <LoadFailure artifact={file.artifact} error={file.error} />}
      {file.status === 'ready' && <Charts key={`${artifact}-${windowId}`} forecast={file.forecast} shown={shown} showMean={showMean} tBands={tBands} logAxis={logAxis} reduced={reduced} />}
      <MetricsTable evaluation={evaluation} shown={shown} />
      <DmResult evaluation={evaluation} shown={shown} />
      <CoverageTable evaluation={evaluation} shown={shown} />
      <footer aria-label="Forecast provenance">
        evaluation: commit {shortCommit(envelope.source_commit)}
        {file.status === 'ready' ? ` · ${artifact}: commit ${shortCommit(file.envelope.source_commit)}` : ''}
      </footer>
    </>
  )
}

// ---- charts ----

type Band = { lower80: number; upper80: number; lower95: number; upper95: number }

/** The exported bounds of one row for the distribution on show: no bound is computed here. */
function bandOf(row: ForecastRow, t: boolean): Band {
  return t
    ? { lower80: row.t_lower_80_usd, upper80: row.t_upper_80_usd, lower95: row.t_lower_95_usd, upper95: row.t_upper_95_usd }
    : { lower80: row.lower_80_usd, upper80: row.upper_80_usd, lower95: row.lower_95_usd, upper95: row.upper_95_usd }
}

/**
 * Pixel scales for a window's rows: the x axis is the row index, the y axis dollars over every value
 * drawn, spaced linearly or, with `log`, by the logarithm of the dollars. Log spacing is a drawing
 * transform (ADR-0001): it places the exported values and computes none of the study's numbers.
 */
function layout(rows: ForecastRow[], bands: Band[], extra: number[], log = false) {
  const ext = extent([rows.map((r) => r.actual_usd), rows.map((r) => r.mean_usd), bands.map((b) => b.lower95), bands.map((b) => b.upper95), extra])
  const [lo, hi] = ext ?? [0, 1]
  const sx = linearScale([0, Math.max(rows.length - 1, 1)], [PAD.l, CHART.width - PAD.r])
  // Up to five dated ticks, evenly spaced over the rows (positions, not values of the study).
  const count = Math.min(5, rows.length)
  const idx = [...new Set(Array.from({ length: count }, (_, k) => (count === 1 ? 0 : Math.round((k * (rows.length - 1)) / (count - 1)))))]
  const xTicks = idx.map((i) => ({ x: sx(i), label: rows[i].date }))
  // Prices are positive; a value that is not would have no place on a log axis, so the axis stays linear.
  if (log && lo > 0) {
    const [a, b] = [Math.log(lo), Math.log(hi)]
    const pad = (b - a) * 0.04 || 0.04
    const toY = linearScale([a - pad, b + pad], [CHART.height - PAD.b, PAD.t])
    const sy = (v: number) => toY(Math.log(v))
    const yTicks = logTicks(Math.exp(a - pad), Math.exp(b + pad), 4).map((v) => ({ y: sy(v), label: formatLogTick(v) }))
    return { sx, sy, yTicks, xTicks, yLabel: 'dollars (adjusted close), log scale' }
  }
  const pad = (hi - lo) * 0.04 || Math.abs(lo) * 0.04 || 1
  const domain: [number, number] = [lo - pad, hi + pad]
  const sy = linearScale(domain, [CHART.height - PAD.b, PAD.t])
  const step = niceStep(domain[1] - domain[0], 4)
  const yTicks = niceTicks(domain[0], domain[1], 4).map((v) => ({ y: sy(v), label: formatTick(v, step) }))
  return { sx, sy, yTicks, xTicks, yLabel: 'dollars (adjusted close)' }
}

function linePath(values: number[], sx: (i: number) => number, sy: (v: number) => number, from = 0): string {
  return values.map((v, i) => `${i === 0 ? 'M' : 'L'}${sx(i + from).toFixed(1)} ${sy(v).toFixed(1)}`).join(' ')
}

/** A closed ribbon: along the upper bounds, back along the lower ones. */
function ribbon(lower: number[], upper: number[], sx: (i: number) => number, sy: (v: number) => number): string {
  if (lower.length === 0) return ''
  const top = upper.map((v, i) => `${i === 0 ? 'M' : 'L'}${sx(i).toFixed(1)} ${sy(v).toFixed(1)}`)
  const bottom = lower.map((v, i) => `L${sx(i).toFixed(1)} ${sy(v).toFixed(1)}`).reverse()
  return `${top.join(' ')} ${bottom.join(' ')} Z`
}

function Axes({ yTicks, xTicks, yLabel }: ReturnType<typeof layout>) {
  return (
    <>
      {yTicks.map((t) => (
        <g key={t.label} className="tick">
          <line className="grid" x1={PAD.l} x2={CHART.width - PAD.r} y1={t.y} y2={t.y} />
          <text x={PAD.l - 6} y={t.y + 3.5} textAnchor="end">
            {t.label}
          </text>
        </g>
      ))}
      {xTicks.map((t) => (
        <text key={t.label} className="tick" x={t.x} y={CHART.height - 8} textAnchor="middle">
          {t.label}
        </text>
      ))}
      <text className="axis-label" x={4} y={13} data-testid="y-label">
        {yLabel}
      </text>
    </>
  )
}

type MarkKind = 'actual' | 'median' | 'mean' | 'rw' | 'band80' | 'band95' | 'now'

/** A legend icon: an SVG with its own width and height, so no stylesheet can stretch it. */
function LegendMark({ kind }: { kind: MarkKind }) {
  return (
    <svg className="legend-mark" viewBox="0 0 12 12" width={12} height={12} style={LEGEND_MARK} aria-hidden="true" data-testid="legend-mark">
      {kind === 'band80' || kind === 'band95' ? (
        <rect className={`fan-${kind}`} x={1} y={2} width={10} height={8} />
      ) : kind === 'now' ? (
        <g className="fan-now">
          <line className="bar95" x1={6} x2={6} y1={1} y2={11} />
          <circle cx={6} cy={6} r={2.5} />
        </g>
      ) : (
        <line className={`line ${kind === 'actual' ? 'line-primary' : kind === 'rw' ? 'line-muted dashed' : kind === 'mean' ? 'line-secondary dashed' : 'line-secondary'}`} x1={1} x2={11} y1={6} y2={6} />
      )}
    </svg>
  )
}

function Legend({ items }: { items: [MarkKind, string][] }) {
  return (
    <figcaption>
      <ul className="plot-legend">
        {items.map(([kind, text]) => (
          <li key={kind}>
            <LegendMark kind={kind} />
            {text}
          </li>
        ))}
      </ul>
    </figcaption>
  )
}

function Charts({ forecast, shown, showMean, tBands, logAxis, reduced }: { forecast: Forecast; shown: Shown; showMean: boolean; tBands: boolean; logAxis: boolean; reduced: boolean }) {
  const win = forecast.windows.find((w) => w.id === shown.windowId) ?? forecast.windows[0]
  const dist = tBands ? 'Student-t (variance-matched)' : 'normal'
  return (
    <>
      <h2>Forecast in dollars</h2>
      <div className="card">
        <FanChart win={win} shown={shown} showMean={showMean} tBands={tBands} logAxis={logAxis} dist={dist} />
        <p className="sub note">
          The median exp(μ) is what the course calls the forecast. The bands are the exported 80% and 95% intervals ({dist}); the Student-t bands use the
          t fitted to the training residuals (df {sig(forecast.t_df, 3)}), scaled to the forecast&apos;s variance.
        </p>
      </div>
      {shown.kind === 'one_step' ? (
        <WalkForward win={win} shown={shown} tBands={tBands} reduced={reduced} />
      ) : (
        <p className="sub note">The walk-forward animation is for the one-step methods: a static path is one forecast, made once, from one origin.</p>
      )}
    </>
  )
}

function FanChart({ win, shown, showMean, tBands, logAxis, dist }: { win: ForecastWindow; shown: Shown; showMean: boolean; tBands: boolean; logAxis: boolean; dist: string }) {
  const rows = win.rows
  const bands = rows.map((r) => bandOf(r, tBands))
  const rw = shown.kind === 'multi_step' ? win.origin.close_usd : null
  const geo = layout(rows, bands, rw === null ? [] : [rw], logAxis)
  const { sx, sy } = geo
  const title = `Forecast of ${shown.modelLabel}, ${shown.methodLabel}, ${WINDOW_LABELS[win.id].toLowerCase()} window ${win.start} to ${win.end}: actual and median price in dollars, with the 80% and 95% ${dist} intervals${logAxis ? ', on a log price axis' : ''}`
  const items: [MarkKind, string][] = [
    ['actual', 'Actual price'],
    ['median', 'Median exp(μ): the course’s forecast'],
    ...(showMean ? ([['mean', 'Mean exp(μ + s²/2)']] as [MarkKind, string][]) : []),
    ['band80', `80% interval (${dist})`],
    ['band95', `95% interval (${dist})`],
    ...(rw === null ? [] : ([['rw', `Random walk: the origin's price, ${usd(rw)} on ${win.origin.date}`]] as [MarkKind, string][])),
  ]
  return (
    <figure className="plot fan">
      <svg viewBox={`0 0 ${CHART.width} ${CHART.height}`} width={CHART.width} height={CHART.height} role="img" aria-label={title} data-testid="fan-chart">
        <Axes {...geo} />
        <path className="fan-band95" d={ribbon(bands.map((b) => b.lower95), bands.map((b) => b.upper95), sx, sy)} data-testid="band-95" />
        <path className="fan-band80" d={ribbon(bands.map((b) => b.lower80), bands.map((b) => b.upper80), sx, sy)} data-testid="band-80" />
        {rw !== null && <line className="line line-muted dashed" x1={sx(0)} x2={sx(Math.max(rows.length - 1, 1))} y1={sy(rw)} y2={sy(rw)} data-testid="rw-line" />}
        <path className="line line-secondary" d={linePath(rows.map((r) => r.median_usd), sx, sy)} data-testid="median-line" />
        {showMean && <path className="line line-secondary dashed" d={linePath(rows.map((r) => r.mean_usd), sx, sy)} data-testid="mean-line" />}
        <path className="line line-primary" d={linePath(rows.map((r) => r.actual_usd), sx, sy)} data-testid="actual-line" />
      </svg>
      <Legend items={items} />
    </figure>
  )
}

/**
 * The one-step forecasts revealed a day at a time. At day i it shows the actual prices up to day i,
 * and the fan for day i (the forecast made the evening before) with the earlier days' fans faded
 * behind it. It starts paused and never plays by itself; with reduced motion it has no timer at all,
 * and the step buttons still move it. A walk that is playing when the reader turns reduced motion on
 * is paused, and stays paused when it is turned off again, until Play is pressed.
 */
function WalkForward({ win, shown, tBands, reduced }: { win: ForecastWindow; shown: Shown; tBands: boolean; reduced: boolean }) {
  const rows = win.rows
  const n = rows.length
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(false)
  // Reduced motion ends the play, not only the timer: otherwise the walk would resume on its own when
  // the preference is turned off (React's adjust-state-while-rendering pattern; no effect needed).
  if (reduced && playing) setPlaying(false)
  const atEnd = cursor >= n - 1
  const running = playing && !reduced && !atEnd
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setCursor((c) => Math.min(c + 1, n - 1)), frameMs(n))
    return () => clearInterval(id)
  }, [running, n])

  const bands = rows.map((r) => bandOf(r, tBands))
  const geo = layout(rows, bands, [])
  const { sx, sy } = geo
  const seen = rows.slice(0, cursor + 1)
  const now = rows[cursor]
  const band = bands[cursor]
  const x = sx(cursor)
  const play = () => {
    if (running) setPlaying(false)
    else {
      if (atEnd) setCursor(0)
      setPlaying(true)
    }
  }
  const step = (by: number) => {
    setPlaying(false)
    setCursor((c) => Math.max(0, Math.min(n - 1, c + by)))
  }
  const title = `Walk-forward forecasts of ${shown.modelLabel}, ${shown.methodLabel}, ${WINDOW_LABELS[win.id].toLowerCase()} window, revealed day by day`
  return (
    <>
      <h2>Walk forward, one day at a time</h2>
      <div className="card">
        <div className="controls walk-controls" role="group" aria-label="Walk-forward animation">
          {/* One pattern: the label says what a press does (Play or Pause); no aria-pressed beside it. */}
          <button type="button" onClick={play} disabled={reduced}>
            {running ? 'Pause' : 'Play'}
          </button>
          <button type="button" onClick={() => step(-1)} disabled={cursor === 0}>
            Step back
          </button>
          <button type="button" onClick={() => step(1)} disabled={atEnd}>
            Step forward
          </button>
          <button
            type="button"
            onClick={() => {
              setPlaying(false)
              setCursor(0)
            }}
          >
            Reset
          </button>
        </div>
        {reduced && <p className="sub note">Your system asks for reduced motion, so the walk does not play by itself; step through it with the buttons.</p>}
        <figure className="plot fan">
          <svg viewBox={`0 0 ${CHART.width} ${CHART.height}`} width={CHART.width} height={CHART.height} role="img" aria-label={title} data-testid="walk-chart">
            <Axes {...geo} />
            <g className="fan-trail" data-testid="walk-trail">
              <path className="fan-band95" d={ribbon(bands.slice(0, cursor).map((b) => b.lower95), bands.slice(0, cursor).map((b) => b.upper95), sx, sy)} />
              <path className="fan-band80" d={ribbon(bands.slice(0, cursor).map((b) => b.lower80), bands.slice(0, cursor).map((b) => b.upper80), sx, sy)} />
              <path className="line line-secondary" d={linePath(rows.slice(0, cursor).map((r) => r.median_usd), sx, sy)} />
            </g>
            <g className="fan-now" data-testid="walk-fan" data-day={cursor}>
              <line className="bar95" x1={x} x2={x} y1={sy(band.lower95)} y2={sy(band.upper95)} />
              <line className="bar80" x1={x} x2={x} y1={sy(band.lower80)} y2={sy(band.upper80)} />
              <circle cx={x} cy={sy(now.median_usd)} r={3.5} />
            </g>
            <path className="line line-primary" d={linePath(seen.map((r) => r.actual_usd), sx, sy)} data-testid="walk-actual" data-points={seen.length} />
            <circle className="walk-actual-dot" cx={x} cy={sy(now.actual_usd)} r={3} />
          </svg>
          <Legend
            items={[
              ['actual', 'Actual price, up to the day on show'],
              ['now', 'That day’s forecast: median, with its 80% and 95% interval'],
              ['band80', 'Earlier days’ intervals, faded'],
            ]}
          />
        </figure>
        {/* Announced when the walk stops (paused, stepped, at the end), not on every day it plays past. */}
        <p className="sub" aria-live={running ? 'off' : 'polite'} data-testid="walk-status">
          Day {cursor + 1} of {n}, {now.date}. Forecast made the evening before: median {usd(now.median_usd)}, 80% {usd(band.lower80)} to {usd(band.upper80)}, 95%{' '}
          {usd(band.lower95)} to {usd(band.upper95)}. Actual {usd(now.actual_usd)}.
        </p>
      </div>
    </>
  )
}

// ---- tables ----

function Reading({ badge, kind, text, span }: { badge: string; kind: string; text: string; span: number }) {
  return (
    <tr className="reading">
      <td colSpan={span}>
        <span className={`verdict verdict-${kind}`}>{badge}</span> {text}
      </td>
    </tr>
  )
}

/** Badge colours keyed by the exported verdict, as on the fit page. */
const DM_TONE: Record<DmVerdict, string> = { beats_rw: 'plain', no_difference: 'inconclusive', worse_than_rw: 'flag', same_as_rw: 'inconclusive' }
const COVERAGE_TONE: Record<CoverageVerdict, string> = { too_narrow: 'flag', consistent: 'plain', too_wide: 'flag', not_tested: 'inconclusive' }

function MetricsTable({ evaluation, shown }: { evaluation: Evaluation; shown: Shown }) {
  const m = evaluation.metrics.find((row) => row.model_id === shown.model && row.method === shown.method && row.window === shown.windowId)
  const rw = evaluation.random_walk.find((row) => row.kind === shown.kind && row.window === shown.windowId)
  // The parser checks both row sets, so neither is ever missing.
  if (!m || !rw) return null
  const ratio = (v: number) => fmt(v, 3)
  const logs = (v: number) => fmt(v, 4)
  const lines: [string, string, string, string][] = [
    ['RMSE, dollars, of the median', usd(m.usd_median.rmse), usd(rw.usd.rmse), ratio(m.ratio_to_rw.usd_median.rmse)],
    ['MAE, dollars, of the median', usd(m.usd_median.mae), usd(rw.usd.mae), ratio(m.ratio_to_rw.usd_median.mae)],
    ['MAPE, of the median', `${fmt(m.usd_median.mape_pct, 2)}%`, `${fmt(rw.usd.mape_pct, 2)}%`, ratio(m.ratio_to_rw.usd_median.mape_pct)],
    ['RMSE, dollars, of the mean', usd(m.usd_mean.rmse), usd(rw.usd.rmse), ratio(m.ratio_to_rw.usd_mean.rmse)],
    ['MAE, dollars, of the mean', usd(m.usd_mean.mae), usd(rw.usd.mae), ratio(m.ratio_to_rw.usd_mean.mae)],
    ['MAPE, of the mean', `${fmt(m.usd_mean.mape_pct, 2)}%`, `${fmt(rw.usd.mape_pct, 2)}%`, ratio(m.ratio_to_rw.usd_mean.mape_pct)],
    ['RMSE, log points', logs(m.log.rmse), logs(rw.log.rmse), ratio(m.ratio_to_rw.log.rmse)],
    ['MAE, log points', logs(m.log.mae), logs(rw.log.mae), ratio(m.ratio_to_rw.log.mae)],
  ]
  const rwText = shown.kind === 'multi_step' ? "static: the origin's price every day" : "one step: yesterday's price"
  return (
    <>
      <h2>Errors against the random walk</h2>
      <div className="card scroll-x">
        <table className="metrics-table">
          <caption>
            Errors of {shown.modelLabel}, {shown.methodLabel}, on the {WINDOW_LABELS[shown.windowId].toLowerCase()} window ({days(m.n)}), beside the random walk ({rwText})
          </caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Model</th>
              <th scope="col">Random walk</th>
              <th scope="col">Ratio</th>
            </tr>
          </thead>
          <tbody>
            {lines.map(([name, model, walk, r]) => (
              <tr key={name}>
                <th scope="row">{name}</th>
                <td className="num">{model}</td>
                <td className="num">{walk}</td>
                <td className="num">{r}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sub note">The ratio is the model&apos;s metric over the random walk&apos;s, as exported: below 1 the model is closer on that metric. The random walk has no spread, so its median and mean are the same price.</p>
        <p className="sub note" aria-label="Back-transform">
          {backTransformSentence(m.back_transform.max_pct, m.back_transform.mean_pct)}
        </p>
      </div>
    </>
  )
}

function DmResult({ evaluation, shown }: { evaluation: Evaluation; shown: Shown }) {
  if (shown.kind === 'multi_step') {
    return (
      <>
        <h2>Diebold–Mariano test</h2>
        <div className="card callout" aria-label="Diebold–Mariano test">
          <p>{DM_STATIC_NOTE}</p>
        </div>
      </>
    )
  }
  const rows: DmRow[] = evaluation.dm.filter((row) => row.model_id === shown.model && row.method === shown.method && row.window === shown.windowId)
  return (
    <>
      <h2>Diebold–Mariano test</h2>
      <div className="card scroll-x">
        <table className="dm-table" aria-label="Diebold–Mariano test">
          <caption>
            Does {shown.modelLabel} ({shown.methodLabel}) have a different expected loss than the random walk on the log errors of the{' '}
            {WINDOW_LABELS[shown.windowId].toLowerCase()} window? Harvey–Leybourne–Newbold corrected, two-sided, read at alpha {evaluation.alpha}
          </caption>
          <thead>
            <tr>
              <th scope="col">Loss</th>
              <th scope="col">Mean difference</th>
              <th scope="col">DM (HLN)</th>
              <th scope="col">df</th>
              <th scope="col">p-value</th>
            </tr>
          </thead>
          {rows.map((row) => (
            <tbody key={row.loss} aria-label={LOSS_LABELS[row.loss]}>
              <tr>
                <th scope="row">{LOSS_LABELS[row.loss]}</th>
                <td className="num">{sig(row.mean_diff, 3)}</td>
                <td className="num">{sig(row.statistic_hln, 4)}</td>
                <td className="num">{row.df}</td>
                <td className="num">
                  <PValue p={row.p_value} />
                </td>
              </tr>
              <Reading badge={DM_LABELS[row.verdict]} kind={DM_TONE[row.verdict]} text={DM_READINGS[row.verdict]} span={5} />
            </tbody>
          ))}
        </table>
        <p className="sub note">
          The mean difference is the model&apos;s mean loss minus the random walk&apos;s, in log points (squared for the squared loss): negative when the model&apos;s loss
          is lower. Each verdict is Python&apos;s.
        </p>
      </div>
    </>
  )
}

function CoverageTable({ evaluation, shown }: { evaluation: Evaluation; shown: Shown }) {
  const rows: CoverageRow[] = evaluation.coverage.filter((row) => row.model_id === shown.model && row.method === shown.method && row.window === shown.windowId)
  return (
    <>
      <h2>Interval coverage</h2>
      <div className="card scroll-x">
        <table className="coverage-table" aria-label="Interval coverage">
          <caption>
            Days of the {WINDOW_LABELS[shown.windowId].toLowerCase()} window whose actual price lies inside each interval of {shown.modelLabel} ({shown.methodLabel}), with
            Kupiec&apos;s test of the nominal level at alpha {evaluation.alpha}
          </caption>
          <thead>
            <tr>
              <th scope="col">Interval</th>
              <th scope="col">Nominal</th>
              <th scope="col">Inside</th>
              <th scope="col">Kupiec LR</th>
              <th scope="col">p-value</th>
            </tr>
          </thead>
          {rows.map((row) => {
            const name = `${DISTRIBUTION_LABELS[row.distribution]}, ${pct(row.level, 0)}`
            return (
              <tbody key={`${row.distribution}-${row.level}`} aria-label={name}>
                <tr>
                  <th scope="row">{name}</th>
                  <td className="num">{pct(row.level, 0)}</td>
                  <td className="num">{insideText(row.inside, row.n, row.rate)}</td>
                  <td className="num">{row.lr === null ? '—' : sig(row.lr, 4)}</td>
                  <td className="num">
                    <PValue p={row.p_value} />
                  </td>
                </tr>
                <Reading badge={COVERAGE_LABELS[row.verdict]} kind={COVERAGE_TONE[row.verdict]} text={COVERAGE_READINGS[row.verdict]} span={5} />
              </tbody>
            )
          })}
        </table>
        <p className="sub note">The levels are {LEVELS.map((l) => pct(l, 0)).join(' and ')}. A day counts as inside when its actual log price lies within the interval; the count is Python&apos;s.</p>
      </div>
    </>
  )
}

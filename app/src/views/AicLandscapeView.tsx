/**
 * The AIC landscape (course module 6, done as ADR-0002 says): every (p, q) cell fitted on the
 * training segment, one d at a time, with failures marked, the choice, BIC's choice and pmdarima's
 * cross-check. Draws aic_grid.json; every number on the page comes from it.
 *
 * Loaded lazily from App.tsx. The 3D scene is a second lazy chunk (three.js), shown only where the
 * browser can make a WebGL2 context; the tables below it hold every value, with or without 3D.
 */
import { lazy, Suspense, useMemo, useState, type ComponentType } from 'react'
import { useLandscapeData, type LandscapeState } from '../data/useOrderData'
import { cellDescription, cellTable, cellText, gridDs, isSelected, modelName, STATUS_LABELS, TREND_LABELS, trendsForD } from '../lib/aicLandscape'
import { motionSettings } from '../lib/aicAxes'
import { hasWebGL, prefersReducedMotion } from '../lib/capabilities'
import { CELL_STATUSES, type AicGrid, type TrendCode } from '../lib/contract.order'
import { describeLoadError } from '../lib/loadError'
import { shortCommit } from '../lib/present'
import { signedFixed } from '../lib/stationarityText'
import { useReducedMotion } from './hooks'
import type { LandscapeSceneProps } from './AicLandscapeScene'
import { SceneBoundary } from './SceneBoundary'

const LazyScene = lazy(() => import('./AicLandscapeScene'))
const MAX_ERRORS_SHOWN = 12

export interface LandscapeOptions {
  webglAvailable?: () => boolean
  readReducedMotion?: () => boolean
  Scene?: ComponentType<LandscapeSceneProps>
}

export default function AicLandscapeView(options: LandscapeOptions) {
  return <AicLandscapePage state={useLandscapeData()} {...options} />
}

/** The page for a given load state; split from the default export so tests can pass any state. */
export function AicLandscapePage({ state, ...options }: { state: LandscapeState } & LandscapeOptions) {
  return (
    <section className="landscape">
      <h2>AIC landscape</h2>
      <p className="sub">
        Every ARIMA(p, d, q) with p and q from 0 to 5, fitted on the training segment. d comes from the unit-root tests on the Stationarity
        page; AIC then ranks p, q and the trend within that one d. The lowest point is the best fit.
      </p>
      <Body state={state} {...options} />
    </section>
  )
}

function Body({ state, ...options }: { state: LandscapeState } & LandscapeOptions) {
  if (state.status === 'loading') {
    return (
      <p className="sub" role="status">
        Loading data/aic_grid.json…
      </p>
    )
  }
  if (state.status === 'error') {
    const lines = describeLoadError(state.error)
    return (
      <div className="card callout error" role="alert">
        <strong>Could not load {state.artifact}.json.</strong>
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
  return <Landscape grid={state.aicGrid} commit={state.envelope.source_commit} {...options} />
}

function Selection({ grid }: { grid: AicGrid }) {
  const s = grid.selection
  const others = s.within_2_aic.filter((w) => !(w.p === s.order[0] && w.q === s.order[2] && w.trend === s.trend))
  const b = s.bic_choice
  return (
    <div className="card callout decision" aria-label="Chosen model">
      <p className="decision-d">
        <strong>{modelName(s.order[0], s.order[1], s.order[2], s.trend)}</strong>
      </p>
      <p>
        AIC {signedFixed(s.aic, 3)} with {s.k_params} parameters, the lowest of the eligible cells at d = {s.d_selected}.{' '}
        {others.length === 0
          ? 'No other eligible cell is within 2 AIC of it.'
          : `Within 2 AIC, about as well supported: ${others.map((w) => `${modelName(w.p, s.d_selected, w.q, w.trend)} (+${w.delta_aic.toFixed(2)})`).join(', ')}.`}
      </p>
      <p>
        BIC, which charges more per parameter, would choose {modelName(b.p, s.d_selected, b.q, b.trend)} (BIC {signedFixed(b.bic, 3)}, against{' '}
        {signedFixed(s.bic, 3)} for the AIC choice).
      </p>
      <p className="sub note">Rule: {s.rule}.</p>
    </div>
  )
}

function Landscape({ grid, commit, webglAvailable = hasWebGL, readReducedMotion = prefersReducedMotion, Scene = LazyScene }: { grid: AicGrid; commit: string } & LandscapeOptions) {
  const ds = gridDs(grid)
  const [d, setD] = useState(grid.selection.d_selected)
  const available = trendsForD(grid, d)
  const [trendChoice, setTrendChoice] = useState<TrendCode | 'all'>('all')
  const trends = useMemo(() => (trendChoice === 'all' || !available.includes(trendChoice) ? available : [trendChoice]), [trendChoice, available])
  const pickD = (x: number) => {
    setD(x)
    setTrendChoice('all')
  }
  const supported = useMemo(() => webglAvailable(), [webglAvailable])
  const reduced = useReducedMotion(readReducedMotion)
  const counts = grid.selection.status_counts.find((c) => c.d === d)
  return (
    <>
      <Selection grid={grid} />
      <div className="card">
        <div className="controls" role="radiogroup" aria-label="Order of differencing">
          <span className="control-label">d</span>
          {ds.map((x) => (
            <button key={x} type="button" role="radio" aria-checked={x === d} className={x === d ? 'toggle on' : 'toggle'} onClick={() => pickD(x)}>
              d = {x}
              {x === grid.selection.d_selected ? ' (chosen)' : ''}
            </button>
          ))}
        </div>
        {available.length > 1 && (
          <div className="controls" role="radiogroup" aria-label="Trend term">
            <span className="control-label">Trend</span>
            {(['all', ...available] as const).map((t) => (
              <button key={t} type="button" role="radio" aria-checked={trendChoice === t} className={trendChoice === t ? 'toggle on' : 'toggle'} onClick={() => setTrendChoice(t)}>
                {t === 'all' ? 'Both' : TREND_LABELS[t]}
              </button>
            ))}
          </div>
        )}
        {d !== grid.selection.d_selected && (
          <p className="callout warn" role="note">
            This is d = {d}. Its AIC values are on their own scale and are never compared with d = {grid.selection.d_selected}: d was chosen by the
            unit-root tests, not by AIC.
          </p>
        )}
        {supported ? (
          <SceneBoundary fallback={<p className="sub">The 3D view could not start in this browser. The table below has every cell.</p>}>
            <Suspense
              fallback={
                <p className="sub" role="status">
                  Loading the 3D landscape…
                </p>
              }
            >
              <Scene grid={grid} d={d} trends={trends} motion={motionSettings(reduced)} />
            </Suspense>
          </SceneBoundary>
        ) : (
          <p className="sub">This browser cannot create a WebGL2 context, so the 3D view is not drawn. The table below has every cell.</p>
        )}
        <ul className="marker-legend" aria-label="Markers">
          <li>
            <span className="mark mark-ok" aria-hidden="true" /> ok: eligible
          </li>
          <li>
            <span className="mark mark-chosen" aria-hidden="true" /> the chosen model
          </li>
          <li>
            <span className="mark mark-not_converged" aria-hidden="true" /> not converged (hollow)
          </li>
          <li>
            <span className="mark mark-near_unit_root" aria-hidden="true" /> near a unit root
          </li>
          <li>
            <span className="mark mark-failed" aria-hidden="true" /> failed: no AIC (a cross on the floor)
          </li>
          {trends.length > 1 && <li>lines: the no-drift surface in grey, the drift surface in the accent colour</li>}
        </ul>
        {counts && (
          <p className="sub note">
            d = {d}: {CELL_STATUSES.map((s) => `${counts[s]} ${STATUS_LABELS[s]}`).join(', ')}. Only ok cells can be chosen. Height runs from the lowest to the
            highest AIC drawn.
          </p>
        )}
      </div>
      {trends.map((trend) => (
        <CellTable key={trend} grid={grid} d={d} trend={trend} />
      ))}
      <BestPerD grid={grid} />
      <PmdarimaCheck grid={grid} />
      <footer aria-label="Landscape provenance">
        aic_grid: commit {shortCommit(commit)} · {grid.fit_settings.library} {grid.fit_settings.version} · {grid.fit_settings.optimizer}, maxiter {grid.fit_settings.maxiter} · near
        unit root above {grid.fit_settings.near_unit_root_threshold} · {grid.n_train.toLocaleString('en-US')} training rows
      </footer>
    </>
  )
}

function CellTable({ grid, d, trend }: { grid: AicGrid; d: number; trend: TrendCode }) {
  const rows = cellTable(grid, d, trend)
  return (
    <>
      <h3 className="table-title">
        d = {d}, {TREND_LABELS[trend]}: ΔAIC from the best eligible cell of d = {d}
      </h3>
      <div className="card scroll-x">
        <table className="aic-table" aria-label={`Delta AIC for d = ${d}, ${TREND_LABELS[trend]}`}>
          <thead>
            <tr>
              <th scope="col" className="corner">p \ q</th>
              {grid.grid.q.map((q) => (
                <th scope="col" key={q}>
                  {q}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={grid.grid.p[i]}>
                <th scope="row">{grid.grid.p[i]}</th>
                {row.map((cell, j) =>
                  cell ? (
                    <td key={j} className={`num status-${cell.status}${isSelected(grid, cell) ? ' chosen' : ''}`} title={cellDescription(cell, isSelected(grid, cell))}>
                      {cellText(cell)}
                      <span className="visually-hidden">: {cellDescription(cell, isSelected(grid, cell))}</span>
                    </td>
                  ) : (
                    <td key={j} />
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sub note">nc: not converged. nu: an inverse AR or MA root above {grid.fit_settings.near_unit_root_threshold}. Hover or focus a cell for its AIC and reason.</p>
      </div>
    </>
  )
}

function BestPerD({ grid }: { grid: AicGrid }) {
  return (
    <>
      <h2>Best eligible cell of each d</h2>
      <div className="card scroll-x">
        <table aria-label="Best eligible cell of each d">
          <thead>
            <tr>
              <th scope="col">d</th>
              <th scope="col">Lowest-AIC ok cell</th>
              <th scope="col">AIC</th>
            </tr>
          </thead>
          <tbody>
            {grid.selection.best_per_d.map((e) => (
              <tr key={e.d}>
                <th scope="row">{e.d}</th>
                <td>{e.cell ? modelName(e.cell.p, e.d, e.cell.q, e.cell.trend) : 'no eligible cell'}</td>
                <td className="num">{e.cell ? signedFixed(e.cell.aic, 3) : '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sub note">
          <strong>AIC is not used to choose d.</strong> Each d scores different observations (d = 0 scores the first day too), and choosing d is a
          unit-root question that AIC&apos;s penalty is not built for (ADR-0002, section 3). This table is for display only.
        </p>
      </div>
    </>
  )
}

function PmdarimaCheck({ grid }: { grid: AicGrid }) {
  const check = grid.pmdarima_check
  return (
    <>
      <h2>Cross-check: pmdarima&apos;s stepwise search</h2>
      {check.status === 'unavailable' ? (
        <p className="card">The pmdarima cross-check is unavailable: {check.reason}.</p>
      ) : (
        <div className="card scroll-x">
          <table aria-label="pmdarima cross-check">
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">pmdarima chose</th>
                <th scope="col">AIC</th>
                <th scope="col">Converged</th>
                <th scope="col">Fits kept</th>
                <th scope="col">Same d</th>
                <th scope="col">Same model</th>
                <th scope="col">AIC gap to our cell</th>
              </tr>
            </thead>
            <tbody>
              {check.runs.map((run) => (
                <tr key={run.label}>
                  <th scope="row">{run.label}</th>
                  <td>{modelName(run.order[0], run.order[1], run.order[2], run.trend)}</td>
                  <td className="num">{signedFixed(run.aic, 3)}</td>
                  <td>{run.converged ? 'yes' : `no, after ${run.iterations} iterations`}</td>
                  <td className="num">{run.visited.length}</td>
                  <td>{run.agreement.d ? 'yes' : 'no'}</td>
                  <td>{run.agreement.order && run.agreement.trend ? 'yes' : 'no'}</td>
                  <td className="num">{run.agreement.aic_gap_same_order === null ? 'no matching cell' : signedFixed(run.agreement.aic_gap_same_order, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="sub note">
            pmdarima {check.version}, on the same training rows. Its stepwise search is local, stops each fit after 50 iterations and hides the fits&apos;
            warnings by default, so it can stop at another model. The gap is its AIC minus ours for the same order and trend.
          </p>
        </div>
      )}
    </>
  )
}

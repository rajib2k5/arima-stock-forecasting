/**
 * Fit and diagnostics (course modules 7 and 8): the three fitted models (the AIC choice, the BIC
 * choice and the course's refit), each with its parameter table, inverse roots on the unit circle,
 * residual tests and residual plots, and the course's recipe with its two problems measured. Draws
 * fit.json and the picked model's residuals_<id>.json; every number on the page comes from them,
 * and every reading is fixed text keyed by a verdict Python exported (ADR-0001).
 *
 * Loaded lazily from App.tsx, so its code and data are fetched only when the page opens; a model's
 * residual file is fetched only when that model is picked.
 */
import { useState } from 'react'
import { useFitData, useResidualsData, type FitState, type Load } from '../data/useFitData'
import type { Envelope } from '../lib/contract'
import { MODEL_IDS, type CancellingPair, type CourseTrack, type Fit, type FitModel, type InvRoot, type ModelId, type ResidualCorrelogram, type Residuals } from '../lib/contract.fit'
import type { CorrelogramBar } from '../lib/correlogram'
import { CorrelogramPlot } from '../lib/CorrelogramPlot'
import {
  ARCH_LABELS,
  ARCH_READINGS,
  ciText,
  clusteringReading,
  EM_DASH,
  MODEL_LABELS,
  modelName,
  NORMALITY_LABELS,
  NORMALITY_READINGS,
  pParts,
  rows,
  sameOrderSentence,
  SERIAL_LABELS,
  SERIAL_READINGS,
  sig,
} from '../lib/fitText'
import { describeLoadError, type ArtifactLoadError } from '../lib/loadError'
import { yearTicks } from '../lib/plot'
import { shortCommit } from '../lib/present'
import { SeriesPlot } from '../lib/SeriesPlot'

const MAX_ERRORS_SHOWN = 12
/**
 * Sizes set on the elements themselves, besides index.css: `.plot svg` is 100% wide, which drew each
 * 12-unit legend icon at 300 px and the 480-unit QQ drawing, text and all, at the card's full width.
 * An inline style outranks any stylesheet rule, and the view test can see it.
 */
const LEGEND_MARK = { width: 12, height: 12 } as const
const QQ_PLOT = { maxWidth: 560 } as const

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

export default function FitView() {
  return <FitPage state={useFitData()} />
}

/**
 * The page for a given load state of fit.json; split from the default export so tests can pass any
 * state. `load` fetches the residual files (tests pass a fake).
 */
export function FitPage({ state, load }: { state: FitState; load?: Load }) {
  return (
    <section className="fit">
      <h2>Fit and diagnostics</h2>
      <p className="sub">
        Three models fitted on the training segment: the AIC choice, the BIC choice and the course&apos;s own refit. For each, the estimates with
        their standard errors, the inverse roots, and the tests a good model&apos;s residuals should pass: no autocorrelation left, and, for
        normal-theory intervals, normality and a constant variance.
      </p>
      <Body state={state} load={load} />
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

function Body({ state, load }: { state: FitState; load?: Load }) {
  if (state.status === 'loading') {
    return (
      <p className="sub" role="status">
        Loading data/fit.json…
      </p>
    )
  }
  if (state.status === 'error') return <LoadFailure artifact={state.artifact} error={state.error} />
  return <Ready fit={state.fit} envelope={state.envelope} load={load} />
}

function Ready({ fit, envelope, load }: { fit: Fit; envelope: Envelope; load?: Load }) {
  const [picked, setPicked] = useState<ModelId>(fit.primary)
  const residuals = useResidualsData(picked, load)
  const model = fit.models.find((m) => m.id === picked) ?? fit.models[0]
  const name = modelName(model.order, model.trend)
  return (
    <>
      <div className="card">
        <div className="controls" role="radiogroup" aria-label="Model">
          <span className="control-label">Model</span>
          {MODEL_IDS.map((id) => (
            <button key={id} type="button" role="radio" aria-checked={id === picked} className={id === picked ? 'toggle on' : 'toggle'} onClick={() => setPicked(id)}>
              {MODEL_LABELS[id]}
              {id === fit.primary ? ' (primary)' : ''}
            </button>
          ))}
        </div>
        <Summary model={model} name={name} />
      </div>
      <ParamTable model={model} name={name} />
      <Roots model={model} name={name} cancelDistance={fit.cancel_distance} />
      <TestTable model={model} name={name} alpha={fit.diagnostic_settings.alpha} />
      <Clustering fit={fit} />
      <Burned model={model} />
      <h2>Residual plots</h2>
      {residuals.status === 'loading' && (
        <p className="sub" role="status">
          Loading data/residuals_{picked}.json…
        </p>
      )}
      {residuals.status === 'error' && <LoadFailure artifact={residuals.artifact} error={residuals.error} />}
      {residuals.status === 'ready' && <ResidualPlots residuals={residuals.residuals} name={name} />}
      <Course track={fit.course_track} />
      <footer aria-label="Fit provenance">
        fit: commit {shortCommit(envelope.source_commit)}
        {residuals.status === 'ready' ? ` · residuals_${picked}: commit ${shortCommit(residuals.envelope.source_commit)}` : ''} · {rows(fit.n_train)} of training data
      </footer>
    </>
  )
}

function Summary({ model, name }: { model: FitModel; name: string }) {
  const info = model.information
  return (
    <div aria-label="Model summary">
      <p>
        <strong>{name}</strong> · {model.label}
      </p>
      <p className="sub note">{model.source}</p>
      <p className="sub note">
        n = {model.nobs.toLocaleString('en-US')} ({model.nobs_effective.toLocaleString('en-US')} in the likelihood after a burn-in of {model.loglikelihood_burn}) · log-likelihood{' '}
        {sig(info.llf, 7)} · AIC {sig(info.aic, 7)} · BIC {sig(info.bic, 7)} · optimiser {model.converged ? 'converged' : 'did not converge'} after {model.iterations}{' '}
        {model.iterations === 1 ? 'iteration' : 'iterations'}
      </p>
      {model.warnings.length > 0 && (
        <ul className="sub note" aria-label="Fit warnings">
          {model.warnings.map((w, i) => (
            <li key={i}>
              {w.category}: {w.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ParamTable({ model, name }: { model: FitModel; name: string }) {
  return (
    <>
      <h2>Parameters</h2>
      <div className="card scroll-x">
        <table className="param-table">
          <caption>Estimates of {name}, with statsmodels&apos; standard errors (outer product of gradients)</caption>
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col">Estimate</th>
              <th scope="col">SE</th>
              <th scope="col">z</th>
              <th scope="col">p-value</th>
              <th scope="col">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {model.params.map((p) => {
              // An error but no z: sigma2, whose test Python leaves out (exported as null).
              const noTest = p.std_err !== null && p.z === null
              return (
                <tr key={p.name}>
                  <th scope="row">
                    <code>{p.name}</code>
                    {p.library_name !== p.name && <span className="sub"> (statsmodels: {p.library_name})</span>}
                  </th>
                  <td className="num">{sig(p.value)}</td>
                  <td className="num">{sig(p.std_err)}</td>
                  <td className="num">{sig(p.z)}</td>
                  <td className="num">
                    <PValue p={p.p_value} />
                    {noTest && <sup aria-label="see the note below the table">†</sup>}
                  </td>
                  <td className="num">{ciText(p.ci_low, p.ci_high)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="sub note">
          z = estimate / SE; the p-value is the chance, if the coefficient were 0, of a z at least this far from 0; the interval is the estimate ± 1.96
          SE. A dash in every column after the estimate marks a parameter whose covariance could not be estimated. Drift and constant in log points
          per day, sigma2 in log points squared.
        </p>
        {model.params.some((p) => p.std_err !== null && p.z === null) && (
          <p className="sub note" aria-label="sigma2 note">
            † sigma2 has a standard error but no z and no p-value: its null value, 0, is on the boundary of what a variance can be, where z is not
            normal, so the test does not apply.
          </p>
        )}
      </div>
    </>
  )
}

const CIRCLE = { size: 260, centre: 130 }

function complexText(root: InvRoot): string {
  if (root.im === 0) return sig(root.re, 3)
  return `${sig(root.re, 3)} ${root.im < 0 ? '−' : '+'} ${Math.abs(root.im).toPrecision(3)}i`
}

/** The inverse roots on the unit circle: AR as filled circles, MA as crosses, Python's cancelling pairs ringed. */
function Roots({ model, name, cancelDistance }: { model: FitModel; name: string; cancelDistance: number }) {
  const { inv_roots_ar: ar, inv_roots_ma: ma, cancelling_pairs: pairs } = model
  // Room for the unit circle, or for the farthest root when one lies outside it.
  const reach = Math.max(1, ...ar.map((r) => r.modulus), ...ma.map((r) => r.modulus))
  const scale = (CIRCLE.centre - 20) / reach
  const x = (r: InvRoot) => CIRCLE.centre + r.re * scale
  const y = (r: InvRoot) => CIRCLE.centre - r.im * scale
  const label = `Inverse roots of ${name} on the unit circle: ${ar.length} AR, ${ma.length} MA, ${pairs.length} cancelling ${pairs.length === 1 ? 'pair' : 'pairs'}`
  return (
    <>
      <h2>Inverse roots</h2>
      <div className="card">
        <figure className="plot unit-circle">
          <svg viewBox={`0 0 ${CIRCLE.size} ${CIRCLE.size}`} role="img" aria-label={label}>
            <line className="grid" x1={10} x2={CIRCLE.size - 10} y1={CIRCLE.centre} y2={CIRCLE.centre} />
            <line className="grid" x1={CIRCLE.centre} x2={CIRCLE.centre} y1={10} y2={CIRCLE.size - 10} />
            <circle className="circle" cx={CIRCLE.centre} cy={CIRCLE.centre} r={scale} />
            {pairs.map((p) => (
              <PairMark key={`${p.ar}-${p.ma}`} a={ar[p.ar]} m={ma[p.ma]} x={x} y={y} />
            ))}
            {ar.map((r, i) => (
              <circle key={`ar-${i}`} className="root-ar" data-testid="root-ar" cx={x(r)} cy={y(r)} r={4.5} />
            ))}
            {ma.map((r, i) => (
              <path key={`ma-${i}`} className="root-ma" data-testid="root-ma" d={`M${x(r) - 4.5} ${y(r) - 4.5} L${x(r) + 4.5} ${y(r) + 4.5} M${x(r) - 4.5} ${y(r) + 4.5} L${x(r) + 4.5} ${y(r) - 4.5}`} />
            ))}
          </svg>
          <figcaption>
            <ul className="plot-legend">
              <li>
                <svg className="legend-mark" viewBox="0 0 12 12" width={12} height={12} style={LEGEND_MARK} aria-hidden="true">
                  <circle className="root-ar" cx={6} cy={6} r={4} />
                </svg>
                AR inverse root
              </li>
              <li>
                <svg className="legend-mark" viewBox="0 0 12 12" width={12} height={12} style={LEGEND_MARK} aria-hidden="true">
                  <path className="root-ma" d="M2 2 L10 10 M2 10 L10 2" />
                </svg>
                MA inverse root
              </li>
              <li>
                <svg className="legend-mark" viewBox="0 0 12 12" width={12} height={12} style={LEGEND_MARK} aria-hidden="true">
                  <circle className="pair-ring" cx={6} cy={6} r={4.5} />
                </svg>
                cancelling pair
              </li>
            </ul>
          </figcaption>
        </figure>
        <RootList title="AR inverse roots" roots={ar} />
        <RootList title="MA inverse roots" roots={ma} />
        <PairList pairs={pairs} ar={ar} ma={ma} cancelDistance={cancelDistance} />
        <p className="sub note">
          Inside the circle the model is stationary (AR) and invertible (MA). An AR root and an MA root close together nearly cancel: the model then
          spends two parameters where it could spend none.
        </p>
      </div>
    </>
  )
}

function PairMark({ a, m, x, y }: { a: InvRoot; m: InvRoot; x: (r: InvRoot) => number; y: (r: InvRoot) => number }) {
  // A ring around the two exported roots and a line between them: drawing, not deciding which roots pair.
  const half = Math.hypot(x(a) - x(m), y(a) - y(m)) / 2
  return (
    <g data-testid="root-pair">
      <circle className="pair-ring" cx={(x(a) + x(m)) / 2} cy={(y(a) + y(m)) / 2} r={Math.max(9, half + 6)} />
      <line className="pair-line" x1={x(a)} y1={y(a)} x2={x(m)} y2={y(m)} />
    </g>
  )
}

function RootList({ title, roots }: { title: string; roots: InvRoot[] }) {
  return (
    <p className="sub note">
      {title}: {roots.length === 0 ? 'none' : roots.map((r) => `${complexText(r)} (modulus ${sig(r.modulus, 3)})`).join(', ')}
    </p>
  )
}

function PairList({ pairs, ar, ma, cancelDistance }: { pairs: CancellingPair[]; ar: InvRoot[]; ma: InvRoot[]; cancelDistance: number }) {
  if (pairs.length === 0) return <p className="sub note">No cancelling pairs: no AR and MA inverse roots lie within {cancelDistance} of each other.</p>
  return (
    <ul className="sub note" aria-label="Cancelling pairs">
      {pairs.map((p) => (
        <li key={`${p.ar}-${p.ma}`} data-testid="pair-item">
          AR root {p.ar + 1} ({complexText(ar[p.ar])}) and MA root {p.ma + 1} ({complexText(ma[p.ma])}): {sig(p.distance, 3)} apart, within {cancelDistance}
        </li>
      ))}
    </ul>
  )
}

function Reading({ badge, kind, text }: { badge: string; kind: string; text: string }) {
  return (
    <tr className="reading">
      <td colSpan={5}>
        <span className={`verdict verdict-${kind}`}>{badge}</span> {text}
      </td>
    </tr>
  )
}

function TestTable({ model, name, alpha }: { model: FitModel; name: string; alpha: number }) {
  const dg = model.diagnostics
  const v = dg.verdicts
  const jb = dg.jarque_bera
  return (
    <>
      <h2>Residual tests</h2>
      <div className="card scroll-x">
        <table className="test-table">
          <caption>
            Tests on the {dg.n.toLocaleString('en-US')} standardised residuals of {name} after the burn-in, each read at alpha {alpha}
          </caption>
          <thead>
            <tr>
              <th scope="col">Test</th>
              <th scope="col">Lag</th>
              <th scope="col">Statistic</th>
              <th scope="col">df</th>
              <th scope="col">p-value</th>
            </tr>
          </thead>
          <tbody aria-label="Ljung–Box">
            {dg.ljung_box.map((row) => (
              <tr key={row.lag}>
                <th scope="row">Ljung–Box</th>
                <td className="num">{row.lag}</td>
                <td className="num">{sig(row.statistic)}</td>
                {row.applied ? (
                  <>
                    <td className="num">{row.df}</td>
                    <td className="num">
                      <PValue p={row.p_value} />
                    </td>
                  </>
                ) : (
                  <td colSpan={2} className="sub">
                    not applied (lag ≤ p + q = {row.model_df})
                  </td>
                )}
              </tr>
            ))}
            <Reading badge={SERIAL_LABELS[v.serial_correlation]} kind={v.serial_correlation === 'found' ? 'flag' : 'plain'} text={SERIAL_READINGS[v.serial_correlation]} />
          </tbody>
          <tbody aria-label="Jarque–Bera">
            <tr>
              <th scope="row">
                Jarque–Bera <span className="sub">skew {sig(jb.skew, 3)}, kurtosis {sig(jb.kurtosis, 3)} (a normal has 0 and 3)</span>
              </th>
              <td className="num">{EM_DASH}</td>
              <td className="num">{sig(jb.statistic)}</td>
              <td className="num">{EM_DASH}</td>
              <td className="num">
                <PValue p={jb.p_value} />
              </td>
            </tr>
            <Reading badge={NORMALITY_LABELS[v.normality]} kind={v.normality === 'rejected' ? 'flag' : 'plain'} text={NORMALITY_READINGS[v.normality]} />
          </tbody>
          <tbody aria-label="ARCH-LM">
            {dg.arch_lm.map((row) => (
              <tr key={row.lags}>
                <th scope="row">ARCH-LM</th>
                <td className="num">{row.lags}</td>
                <td className="num">{sig(row.statistic)}</td>
                <td className="num">{EM_DASH}</td>
                <td className="num">
                  <PValue p={row.p_value} />
                </td>
              </tr>
            ))}
            <Reading badge={ARCH_LABELS[v.arch]} kind={v.arch === 'found' ? 'flag' : 'plain'} text={ARCH_READINGS[v.arch]} />
          </tbody>
        </table>
        <p className="sub note">
          Ljung–Box takes p + q degrees of freedom off each lag, so a lag at or below p + q has none left and is not tested. ARCH-LM is Engle&apos;s (n − m) R²
          from regressing the squared residuals on their own m lags, with n − m the rows of that regression. Each verdict is Python&apos;s: a test rejects when any of its rows does at alpha,
          with no adjustment for testing several lags.
        </p>
      </div>
    </>
  )
}

function Clustering({ fit }: { fit: Fit }) {
  const cp = fit.clustering_prediction
  return (
    <div className={cp.confirmed ? 'card callout decision' : 'card callout decision conflict'} aria-label="Clustering prediction">
      <p>
        <strong>Volatility clustering, tested on the {MODEL_LABELS[cp.model_id]}.</strong> {clusteringReading(cp.confirmed)}
      </p>
      <p className="sub note">
        ARCH-LM rejects at {cp.arch_lm_rejections} of {fit.diagnostic_settings.arch_lm_lags.length} lags; {cp.acf_squared_outside_count} of{' '}
        {fit.diagnostic_settings.nlags} squared-residual ACF bars lie past their band, against {sig(cp.acf_squared_expected_by_chance, 3)} expected by
        chance (alpha × nlags).
      </p>
    </div>
  )
}

function Burned({ model }: { model: FitModel }) {
  const dg = model.diagnostics
  if (dg.burned.length === 0) return null
  return (
    <div className="card callout warn" role="note" aria-label="Burned residuals">
      {dg.burned.map((b) => (
        <p key={b.date}>
          statsmodels leaves the residual of {b.date} out of the likelihood and these tests: it is {sig(b.resid, 3)} log points ({sig(b.resid_std, 3)}{' '}
          standardised), against a largest |residual| of {sig(dg.max_abs_resid_after_burn, 3)} after the burn-in. The course&apos;s plots include this
          first residual.
        </p>
      ))}
    </div>
  )
}

function bars(g: ResidualCorrelogram): CorrelogramBar[] {
  // Python's band and Python's flag for each lag, passed through as exported.
  return g.rows.map((row) => ({ lag: row.lag, value: row.acf, band: g.band, outside: row.outside }))
}

function ResidualPlots({ residuals, name }: { residuals: Residuals; name: string }) {
  const res = residuals
  const xs = res.rows.map((_, i) => i)
  const dates = res.rows.map((r) => r.date)
  const qx = res.qq.map((p) => p.theoretical)
  return (
    <div className="card">
      <h3>Standardised residuals over time</h3>
      <SeriesPlot
        title={`Standardised residuals of ${name}, ${dates[0]} to ${dates[dates.length - 1]}`}
        xs={xs}
        series={[{ name: 'Standardised residual', ys: res.rows.map((r) => r.resid_std), tone: 'primary' }]}
        yLabel="standardised residual"
        xTicks={yearTicks(dates).map((t) => ({ x: t.index, label: t.label }))}
        zeroLine
        readout={(i) => `${res.rows[i].date} · ${sig(res.rows[i].resid_std, 3)}`}
      />
      <div className="panel-grid">
        <div className="panel">
          <h3>ACF of the residuals</h3>
          <CorrelogramPlot title={`ACF of the standardised residuals, lags 1 to ${res.nlags}`} label="ACF" bars={bars(res.acf)} />
          <p className="sub note">
            Past the band: {res.acf.outside_count} of {res.nlags} lags.
          </p>
        </div>
        <div className="panel">
          <h3>ACF of the squared residuals</h3>
          <CorrelogramPlot title={`ACF of the squared standardised residuals, lags 1 to ${res.nlags}`} label="ACF of squares" bars={bars(res.acf_squared)} />
          <p className="sub note">
            Past the band: {res.acf_squared.outside_count} of {res.nlags} lags.
          </p>
        </div>
      </div>
      <p className="sub note">
        n = {res.n.toLocaleString('en-US')} after a burn-in of {res.burn_excluded}; band z / √n = {sig(res.acf.band, 4)} at every lag, z ={' '}
        {res.z.toFixed(2)}. Squared residuals that are correlated mean the size of a move depends on the size of recent moves.
      </p>
      <h3>QQ plot</h3>
      {/* Capped so that its 480-unit drawing, and so its text, is not scaled up to the card's width. */}
      <div className="qq-plot" style={QQ_PLOT}>
        <SeriesPlot
          title="QQ plot of the sorted standardised residuals against normal quantiles, with the fitted Student-t"
          xs={qx}
          series={[
            { name: 'Sorted standardised residuals', ys: res.qq.map((p) => p.sample), tone: 'primary' },
            { name: `Fitted Student-t quantiles (df ${sig(res.t_fit.df, 3)})`, ys: res.qq.map((p) => p.t_theoretical), tone: 'secondary', dashed: true },
            // y = x through the exported normal quantiles: a reference line, drawn, not computed.
            { name: 'y = x (a normal sample)', ys: qx, tone: 'muted' },
          ]}
          yLabel="residual quantile"
          width={480}
          height={300}
          readout={(i) => `normal ${sig(res.qq[i].theoretical, 3)} · residual ${sig(res.qq[i].sample, 3)} · Student-t ${sig(res.qq[i].t_theoretical, 3)}`}
        />
      </div>
      <p className="sub note">
        Points above the line on the right and below it on the left are heavy tails. Student-t fitted by maximum likelihood: df {sig(res.t_fit.df, 3)}, loc{' '}
        {sig(res.t_fit.loc, 3)}, scale {sig(res.t_fit.scale, 3)}.
      </p>
    </div>
  )
}

function Course({ track }: { track: CourseTrack }) {
  const dd = track.drift_dropped
  return (
    <>
      <h2>The course&apos;s recipe</h2>
      <div className="card" aria-label="Course track">
        <p>{sameOrderSentence(track)}</p>
        <p>
          The course runs auto_arima (pmdarima {track.pmdarima_version}) on the full series of {rows(track.n_course)}, not on the {rows(track.n_train)} of the
          training split, so its search saw <strong>{track.test_rows_seen}</strong> test {track.test_rows_seen === 1 ? 'row' : 'rows'}.
        </p>
        <p>
          auto_arima picked trend {dd.selected_trend ?? EM_DASH}, but the course then refits with <code>ARIMA(train, order).fit()</code>, whose trend is{' '}
          {dd.refit_trend}: the drift is dropped. Refitted with a drift, the course order has AIC {sig(dd.aic_with_drift, 7)} against {sig(dd.aic_without_drift, 7)}{' '}
          without it (without − with = {sig(dd.aic_gap, 4)}); the drift is {sig(dd.drift, 3)} log points per day, SE {sig(dd.drift_std_err, 3)}, p-value{' '}
          <PValue p={dd.drift_p_value} />.
        </p>
      </div>
    </>
  )
}

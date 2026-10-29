/**
 * Stationarity and identification (course modules 5 and 6): the ADF and KPSS table for d = 0, 1
 * and 2, the decision on d, and the ACF and PACF with their 95% bands. Draws stationarity.json and
 * acf_pacf.json; every number on the page comes from them.
 *
 * Loaded lazily from App.tsx, so its code and data are fetched only when the page opens.
 */
import { useState } from 'react'
import { useStationarityData, type StationarityState } from '../data/useOrderData'
import type { AcfPacf, Stationarity, StationarityTransform, TestPair } from '../lib/contract.order'
import { correlogramBars } from '../lib/correlogram'
import { CorrelogramPlot } from '../lib/CorrelogramPlot'
import { describeLoadError } from '../lib/loadError'
import { shortCommit } from '../lib/present'
import { adfLag, decisionSentence, formatP, kpssP, ndiffsSentence, signedFixed, TRANSFORM_LABELS, VERDICT_LABELS, VERDICT_MEANINGS } from '../lib/stationarityText'

const MAX_ERRORS_SHOWN = 12

export default function StationarityView() {
  return <StationarityPage state={useStationarityData()} />
}

/** The page for a given load state; split from the default export so tests can pass any state. */
export function StationarityPage({ state }: { state: StationarityState }) {
  return (
    <section className="stationarity">
      <h2>Stationarity and identification</h2>
      <p className="sub">
        Is the log price a random walk, and how many differences make it stationary? Two tests with opposite null hypotheses decide d, on
        the training segment only. The ACF and PACF of the chosen series then hint at p and q; the AIC landscape decides them.
      </p>
      <Body state={state} />
    </section>
  )
}

function Body({ state }: { state: StationarityState }) {
  if (state.status === 'loading') {
    return (
      <p className="sub" role="status">
        Loading data/stationarity.json and data/acf_pacf.json…
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
  const { stationarity: st, acfPacf } = state
  return (
    <>
      <Decision st={st} />
      <TestTable st={st} />
      <TwoByTwo />
      <Correlograms st={st} acfPacf={acfPacf} />
      <footer aria-label="Stationarity provenance">
        stationarity: commit {shortCommit(state.envelopes.stationarity.source_commit)} · acf_pacf: commit {shortCommit(state.envelopes.acf_pacf.source_commit)} · {st.n_train.toLocaleString('en-US')}{' '}
        training rows
      </footer>
    </>
  )
}

function Decision({ st }: { st: Stationarity }) {
  const d = st.decision
  return (
    <div className={d.tests_conflict ? 'card callout decision conflict' : 'card callout decision'} aria-label="Decision on d">
      <p className="decision-d">
        d = <strong>{d.d_selected}</strong>
      </p>
      <p>{decisionSentence(st)}</p>
      <p className="sub note">Rule: {d.rule}</p>
      <p className="sub note">{ndiffsSentence(d.pmdarima_ndiffs, d.d_selected)}</p>
    </div>
  )
}

function pairCells(pair: TestPair) {
  return (
    <>
      <td className="num">{signedFixed(pair.adf.statistic, 3)}</td>
      <td className="num">{formatP(pair.adf.p_value)}</td>
      <td className="num">{adfLag(pair.adf)}</td>
      <td className="num">{pair.kpss.statistic.toFixed(4)}</td>
      <td className="num">{kpssP(pair.kpss)}</td>
      <td className="num">{pair.kpss.nlags}</td>
      <td>
        <span className={`verdict verdict-${pair.verdict}`}>{VERDICT_LABELS[pair.verdict]}</span>
      </td>
    </>
  )
}

function TestRows({ transforms, chosen, pick }: { transforms: StationarityTransform[]; chosen: number; pick: (t: StationarityTransform) => TestPair }) {
  return (
    <tbody>
      {transforms.map((t) => (
        <tr key={t.id} className={t.d === chosen ? 'chosen' : undefined} aria-current={t.d === chosen ? 'true' : undefined}>
          <th scope="row">
            {TRANSFORM_LABELS[t.id]} <span className="sub">d = {t.d}</span>
          </th>
          <td className="num">{t.n.toLocaleString('en-US')}</td>
          {pairCells(pick(t))}
        </tr>
      ))}
    </tbody>
  )
}

function TableHead() {
  return (
    <thead>
      <tr>
        <th scope="col">Series</th>
        <th scope="col">n</th>
        <th scope="col">ADF τ</th>
        <th scope="col">ADF p</th>
        <th scope="col">ADF lag</th>
        <th scope="col">KPSS η</th>
        <th scope="col">KPSS p</th>
        <th scope="col">KPSS lags</th>
        <th scope="col">Verdict</th>
      </tr>
    </thead>
  )
}

function TestTable({ st }: { st: Stationarity }) {
  const first = st.transforms[0]
  return (
    <>
      <h2>Unit-root tests, training segment</h2>
      <div className="card scroll-x">
        <table aria-label="ADF and KPSS with a constant">
          <TableHead />
          <TestRows transforms={st.transforms} chosen={st.decision.d_selected} pick={(t) => t} />
        </table>
        <p className="sub note">
          Both tests with a constant (<code>regression=&apos;c&apos;</code>), the rule&apos;s setting. ADF chooses its lag by AIC; KPSS chooses its bandwidth
          automatically. A KPSS p shown as ≤ 0.01 or ≥ 0.10 was clipped to the edge of statsmodels&apos; table. 5% critical values: ADF{' '}
          {signedFixed(first.adf.critical_values['5%'], 3)}, KPSS {first.kpss.critical_values['5%'].toFixed(3)}. Rejection uses p &lt; {st.alpha}.
        </p>
      </div>
      <details className="card">
        <summary>With a linear trend as well (regression &apos;ct&apos;): reported, never used by the rule</summary>
        <div className="scroll-x">
          <table aria-label="ADF and KPSS with a constant and a trend">
            <TableHead />
            <TestRows transforms={st.transforms} chosen={st.decision.d_selected} pick={(t) => t.with_trend} />
          </table>
        </div>
        <p className="sub note">
          A rising price is not stationary around a fixed mean, but it could be stationary around a line. With a trend the alternative is that
          line. 5% critical values: ADF {signedFixed(first.with_trend.adf.critical_values['5%'], 3)}, KPSS{' '}
          {first.with_trend.kpss.critical_values['5%'].toFixed(3)}.
        </p>
      </details>
    </>
  )
}

function TwoByTwo() {
  return (
    <>
      <h2>Reading the two tests together</h2>
      <div className="card scroll-x">
        <table className="two-by-two" aria-label="The two by two table">
          <thead>
            <tr>
              <th scope="col" />
              <th scope="col">KPSS does not reject</th>
              <th scope="col">KPSS rejects</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">ADF rejects</th>
              <td>
                <span className="verdict verdict-stationary">{VERDICT_LABELS.stationary}</span> {VERDICT_MEANINGS.stationary}
              </td>
              <td>
                <span className="verdict verdict-conflict">{VERDICT_LABELS.conflict}</span> {VERDICT_MEANINGS.conflict}
              </td>
            </tr>
            <tr>
              <th scope="row">ADF does not reject</th>
              <td>
                <span className="verdict verdict-inconclusive">{VERDICT_LABELS.inconclusive}</span> {VERDICT_MEANINGS.inconclusive}
              </td>
              <td>
                <span className="verdict verdict-unit_root">{VERDICT_LABELS.unit_root}</span> {VERDICT_MEANINGS.unit_root}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  )
}

function Correlograms({ st, acfPacf }: { st: Stationarity; acfPacf: AcfPacf }) {
  const [d, setD] = useState(st.decision.d_selected)
  const series = acfPacf.series.find((s) => s.d === d) ?? acfPacf.series[0]
  const acf = correlogramBars(series, 'acf')
  const pacf = correlogramBars(series, 'pacf')
  const name = TRANSFORM_LABELS[series.transform].toLowerCase()
  return (
    <>
      <h2>ACF and PACF</h2>
      <p className="sub">
        The course draws these for the differenced series to guess p and q. The shaded band is the 95% band around zero; a bar past it is
        drawn in the accent colour.
      </p>
      <div className="card">
        <div className="controls" role="radiogroup" aria-label="Series for the ACF and PACF">
          <span className="control-label">Series</span>
          {acfPacf.series.map((s) => (
            <button key={s.d} type="button" role="radio" aria-checked={s.d === series.d} className={s.d === series.d ? 'toggle on' : 'toggle'} onClick={() => setD(s.d)}>
              d = {s.d}
              {s.d === st.decision.d_selected ? ' (chosen)' : ''}
            </button>
          ))}
        </div>
        <div className="panel-grid">
          <div className="panel">
            <h3>ACF of the {name}</h3>
            <CorrelogramPlot title={`ACF of the ${name}, lags 1 to ${acfPacf.nlags}`} label="ACF" bars={acf} />
          </div>
          <div className="panel">
            <h3>PACF of the {name}</h3>
            <CorrelogramPlot title={`PACF of the ${name}, lags 1 to ${acfPacf.nlags}`} label="PACF" bars={pacf} />
          </div>
        </div>
        <p className="sub note">
          n = {series.n.toLocaleString('en-US')}, z = {acfPacf.z.toFixed(2)}. ACF band (Bartlett): z × √((1 + 2 × (r₁² + … + rₖ₋₁²)) / n), so it widens
          with the lag. PACF band: z / √n = {series.rows[1].pacf_band.toFixed(4)} at every lag. Past the band: {series.acf_outside_count} of {acf.length} ACF lags
          and {series.pacf_outside_count} of {pacf.length} PACF lags. With independent noise about 1 lag in 20 would be; volatility clustering makes the
          real band wider than this one. Lag 0 is 1 by definition and is not drawn. Settings: <code>fft={String(acfPacf.acf_settings.fft)}</code>,{' '}
          <code>method=&apos;{acfPacf.pacf_method}&apos;</code>, as <code>plot_acf</code> and <code>plot_pacf</code> use.
        </p>
      </div>
    </>
  )
}

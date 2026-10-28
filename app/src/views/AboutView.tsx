/**
 * About page: what the project is, the analysis path, what it adds, plus the study facts
 * (ticker, windows, milestones) and provenance read from `meta.json` through the contract.
 */
import type { MetaState } from '../data/useMeta'
import { describeLoadError } from '../lib/loadError'
import { formatWindow, shortCommit, statusLabel } from '../lib/present'

const CREDIT =
  'Module structure follows the "Stock Price Forecasting Using ARIMA Model in Python" sample course outline; all code and text here are our own.'

const PATH: { name: string; what: string }[] = [
  { name: 'Data acquisition', what: 'Download daily prices once and cache the raw file outside the repository.' },
  { name: 'Preprocessing', what: 'Line the series up on trading days, carry the last close across gaps, take the log of the close.' },
  { name: 'Exploratory data analysis', what: 'Look at price, log price, returns and volatility before fitting anything.' },
  { name: 'Stationarity (ADF)', what: 'Test for a unit root with the Augmented Dickey-Fuller test; difference until it goes away.' },
  { name: 'ACF/PACF and automatic order search', what: 'Read the correlograms, then let an information-criterion search propose (p, d, q).' },
  { name: '90/10 split', what: 'Fit on the first 90% of the observations and hold out the last 10% for testing.' },
  { name: 'ARIMA fit', what: 'Estimate the chosen model on the training part only.' },
  { name: 'Residual diagnostics', what: 'Check that what is left over looks like noise: no remaining autocorrelation, roughly bell-shaped.' },
  { name: 'Static multi-step forecast', what: 'Forecast the whole test period in one go from the last training day.' },
  { name: 'RMSE / MAE / MAPE', what: 'Score the forecast against what actually happened.' },
]

const ADDS: { name: string; what: string }[] = [
  { name: 'Walk-forward one-step forecasts', what: 'Re-forecast one day ahead, every day, the way a forecaster would use the model, instead of one long static forecast.' },
  { name: 'A random-walk baseline', what: '"Tomorrow equals today": the bar any ARIMA model has to clear to be worth its complexity.' },
  { name: 'KPSS alongside ADF', what: 'The two tests have opposite null hypotheses (ADF: a unit root; KPSS: stationarity), so when they agree the answer is more convincing than either alone.' },
  {
    name: 'A "where the sample goes wrong" note',
    what: 'Explains the four places the sample course goes wrong (choosing the order with the test data in view, calling one long static forecast a forecast, reporting an error with nothing to compare it to, and reading the exponentiated log forecast as the mean price when it is the median) and measures what each one costs.',
  },
  { name: 'Order selection on the training split only', what: 'The (p, d, q) search never sees the test data, so the test scores are not flattered by it.' },
]

export function AboutView({ state }: { state: MetaState }) {
  return (
    <section className="about">
      <h2>About</h2>
      <p className="sub">
        A learning repository about forecasting a stock price with ARIMA models, done carefully. Python computes everything and writes
        versioned JSON; this app never computes a result, it only draws what that JSON says.
      </p>

      <h2>The data</h2>
      <DataFacts state={state} />

      <h2>The analysis path</h2>
      <p className="sub">Ten modules, in order.</p>
      <ol className="steps" aria-label="Analysis path">
        {PATH.map((m) => (
          <li key={m.name}>
            <strong>{m.name}</strong>
            <span>{m.what}</span>
          </li>
        ))}
      </ol>

      <h2>What this repo adds</h2>
      <ul className="steps" aria-label="Additions to the course path">
        {ADDS.map((m) => (
          <li key={m.name}>
            <strong>{m.name}</strong>
            <span>{m.what}</span>
          </li>
        ))}
      </ul>

      <p className="sub credit">{CREDIT}</p>
      <p className="callout card" role="note">
        <strong>Not financial advice.</strong> This is an educational study of a statistical method. Nothing here is a recommendation
        to buy or sell anything.
      </p>

      {state.status === 'ready' && (
        <footer aria-label="Data provenance">
          schema {state.envelope.schema_version} · generated {state.envelope.generated_at} · commit {shortCommit(state.envelope.source_commit)}
        </footer>
      )}
    </section>
  )
}

function DataFacts({ state }: { state: MetaState }) {
  if (state.status === 'loading') {
    return (
      <p className="sub" role="status">
        Loading data/meta.json…
      </p>
    )
  }
  if (state.status === 'error') {
    return (
      <div className="card callout error" role="alert">
        <strong>Could not load the study data.</strong>
        <ul>
          {describeLoadError(state.error).map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
        <p>
          Run <code>uv run python tools/export_app_data.py</code> from the repository root to generate{' '}
          <code>app/public/data/meta.json</code>, then reload this page.
        </p>
      </div>
    )
  }
  const { meta } = state
  return (
    <>
      <div className="grid">
        <div className="stat">
          <div className="k">Ticker</div>
          <div className="v">{meta.ticker}</div>
        </div>
        <div className="stat">
          <div className="k">Course window</div>
          <div className="v v-sm">{formatWindow(meta.windows.course)}</div>
        </div>
        <div className="stat">
          <div className="k">Out-of-sample window</div>
          <div className="v v-sm">{formatWindow(meta.windows.oos)}</div>
        </div>
      </div>
      <p className="sub">
        The course window follows the sample course outline. The out-of-sample window starts where it ends, so it is data the
        course path never saw.
      </p>
      <h2>Milestones</h2>
      <ol className="milestones" aria-label="Milestones">
        {meta.milestones.map((m) => (
          <li key={m.id}>
            <span className={`badge status-${m.status}`}>{statusLabel(m.status)}</span>
            <span>
              {m.id}. {m.title}
            </span>
          </li>
        ))}
      </ol>
    </>
  )
}

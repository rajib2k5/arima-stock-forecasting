/**
 * Price explorer: the first view driven by data. It draws prices.json (the adjusted close of every
 * trading day, with the train, test and out-of-sample segments shaded) and eda.json (two KDEs and a
 * four-part decomposition of the training split).
 *
 * Loaded lazily from App.tsx, so its code and its two data files are fetched only when the reader
 * opens this page. Every number on it comes from the JSON; the view formats, it never computes.
 */
import { useState } from 'react'
import { useExplorerData, type ExplorerState } from '../data/useExplorerData'
import { SEGMENTS, type Eda, type Prices } from '../lib/contract.payloads'
import { describeLoadError, looksAbsent } from '../lib/loadError'
import {
  DECOMPOSITION_PARTS,
  SEGMENT_LABELS,
  decompositionXTicks,
  kdeMeta,
  kdePlot,
  nullEnds,
  orderedKdes,
  pricePlot,
  shortSha,
  signed,
  usd,
  type Axis,
} from '../lib/explorer'
import { shortCommit } from '../lib/present'
import { SeriesPlot } from '../lib/SeriesPlot'

const MAX_ERRORS_SHOWN = 12
// Panels sit two to a row, so their drawings are half the main chart's width (text stays readable).
const PANEL_WIDTH = 420

export default function PriceExplorerView({ held = [] }: { held?: readonly string[] }) {
  return <PriceExplorer state={useExplorerData()} held={held} />
}

/** The page for a given load state; split from the default export so tests can pass any state. */
export function PriceExplorer({ state, held = [] }: { state: ExplorerState; held?: readonly string[] }) {
  return (
    <section className="explorer">
      <h2>Price explorer</h2>
      <p className="sub">
        The adjusted daily close of the study, with the three segments shaded. Only the training segment is described below: looking
        closely at the test or out-of-sample data before choosing a model would let it shape the choice.
      </p>
      <ExplorerBody state={state} held={held} />
    </section>
  )
}

function ExplorerBody({ state, held }: { state: ExplorerState; held: readonly string[] }) {
  if (state.status === 'loading') {
    return (
      <p className="sub" role="status">
        Loading data/prices.json and data/eda.json…
      </p>
    )
  }
  // A held artifact (meta.held_artifacts: written by the export, not committed) that is simply not
  // there gets instructions, not an error. Any other failure is a real error and is shown as one.
  if (state.status === 'error' && held.includes(state.artifact) && looksAbsent(state.error)) {
    return (
      <div className="card callout" role="status" aria-label="Data not built here">
        <strong>The price data is not built in this copy.</strong>
        <p>
          <code>prices.json</code> and <code>eda.json</code> are not committed: whether Yahoo-derived prices may be published in this
          repository is still the owner&apos;s decision (ADR-0001). Build them on your machine, from the repository root:
        </p>
        <ol>
          <li>
            <code>uv run python tools/fetch_prices.py</code>
          </li>
          <li>
            <code>uv run python tools/export_app_data.py</code>
          </li>
        </ol>
        <p className="sub note">Then reload this page. (What the app saw: {describeLoadError(state.error).join(' ')})</p>
      </div>
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
          Run <code>uv run python tools/fetch_prices.py</code>, then <code>uv run python tools/export_app_data.py</code>, from the
          repository root, and reload this page.
        </p>
      </div>
    )
  }
  return (
    <>
      <PriceChart prices={state.prices} />
      <Distributions eda={state.eda} />
      <Decomposition eda={state.eda} />
      <SummaryTable eda={state.eda} />
      <footer aria-label="Explorer provenance">
        prices: snapshot {shortSha(state.prices.source.raw_sha256)} · downloaded {state.prices.source.downloaded_at} · yfinance{' '}
        {state.prices.source.yfinance_version} · commit {shortCommit(state.envelopes.prices.source_commit)}
      </footer>
    </>
  )
}

function PriceChart({ prices }: { prices: Prices }) {
  const [axis, setAxis] = useState<Axis>('usd')
  const plot = pricePlot(prices, axis)
  return (
    <div className="card">
      <div className="controls" role="radiogroup" aria-label="Price axis">
        <span className="control-label">Axis</span>
        {(
          [
            ['usd', 'Dollars'],
            ['log', 'Log price'],
          ] as const
        ).map(([value, label]) => (
          <button key={value} type="button" role="radio" aria-checked={axis === value} className={axis === value ? 'toggle on' : 'toggle'} onClick={() => setAxis(value)}>
            {label}
          </button>
        ))}
      </div>
      <SeriesPlot
        title={`${prices.ticker} ${axis === 'usd' ? 'adjusted close in dollars' : 'log of the adjusted close'}, ${prices.rows[0].date} to ${prices.rows[prices.rows.length - 1].date}`}
        xs={plot.xs}
        series={plot.series}
        yLabel={plot.yLabel}
        bands={plot.bands}
        xTicks={plot.xTicks}
        height={300}
        readout={plot.readout}
      />
      <ul className="segment-legend" aria-label="Segments">
        {SEGMENTS.map((name) => {
          const span = prices.splits[name]
          return (
            <li key={name}>
              <span className={`swatch band-${name}`} aria-hidden="true" />
              <strong>{SEGMENT_LABELS[name]}</strong> {span.start} to {span.end} · {span.n.toLocaleString('en-US')} {span.n === 1 ? 'day' : 'days'}
            </li>
          )
        })}
      </ul>
      <p className="sub note">
        Train and test split the course window {Math.round(prices.splits.train_fraction * 100)}/{100 - Math.round(prices.splits.train_fraction * 100)} by
        position. The x axis counts trading days, so weekends and holidays take no space. Hover, or focus the chart and use the arrow
        keys, to read single days. {prices.fill.filled_dates.length === 0 ? 'No close needed forward-filling.' : `Forward-filled closes: ${prices.fill.filled_dates.join(', ')}.`}
      </p>
    </div>
  )
}

function Distributions({ eda }: { eda: Eda }) {
  return (
    <>
      <h2>Distributions, training segment</h2>
      <div className="panel-grid">
        {orderedKdes(eda).map((kde) => {
          const meta = kdeMeta(kde.variable)
          const plot = kdePlot(kde)
          return (
            <div className="card panel" key={kde.variable}>
              <h3>{meta.title}</h3>
              <SeriesPlot title={`Kernel density of ${meta.title.toLowerCase()}`} xs={plot.xs} series={plot.series} yLabel="density" width={PANEL_WIDTH} height={230} readout={plot.readout} />
              <p className="sub note">
                n = {kde.n.toLocaleString('en-US')} · Gaussian kernel · bandwidth ({kde.bandwidth_method}) {kde.bandwidth.toPrecision(3)} {meta.xLabel}
              </p>
            </div>
          )
        })}
      </div>
    </>
  )
}

function Decomposition({ eda }: { eda: Eda }) {
  const { rows, period, model } = eda.decomposition
  const xs = rows.map((_, i) => i)
  const ticks = decompositionXTicks(rows)
  const ends = nullEnds(rows)
  return (
    <>
      <h2>Decomposition of the log price, training segment</h2>
      <p className="sub">
        Classical {model} decomposition with a period of {period} trading days: observed = trend + seasonal + residual, all in log points.
        The trend is a centred moving average, so it is undefined for the first {ends.head} and last {ends.tail} days. The course runs a
        multiplicative decomposition on the log; the milestone 1 walkthrough explains why additive on logs is the right reading.
      </p>
      <div className="panel-grid">
        {DECOMPOSITION_PARTS.map((part) => (
          <div className="card panel" key={part.key}>
            <h3>{part.title}</h3>
            <SeriesPlot
              title={`${part.title} of the log price`}
              xs={xs}
              series={[{ name: part.title, ys: rows.map((r) => r[part.key]), tone: part.tone }]}
              yLabel="ln($)"
              xTicks={ticks}
              width={PANEL_WIDTH}
              height={190}
              zeroLine={part.key === 'seasonal_log' || part.key === 'resid_log'}
              readout={(i) => {
                const v = rows[i][part.key]
                return `${rows[i].date} · ${v === null ? 'undefined' : signed(v, 4)}`
              }}
            />
          </div>
        ))}
      </div>
    </>
  )
}

function SummaryTable({ eda }: { eda: Eda }) {
  const { summary } = eda
  const rows: [string, string][] = [
    ['Trading days', `${summary.n.toLocaleString('en-US')} (${summary.start} to ${summary.end})`],
    ['Close: min / median / mean / max', `${usd(summary.close_usd.min)} / ${usd(summary.close_usd.median)} / ${usd(summary.close_usd.mean)} / ${usd(summary.close_usd.max)}`],
    ['Daily log returns', summary.log_return.n.toLocaleString('en-US')],
    ['Log return: mean', signed(summary.log_return.mean, 6)],
    ['Log return: standard deviation (n − 1)', summary.log_return.std.toFixed(6)],
    ['Log return: skewness (G1)', signed(summary.log_return.skew, 3)],
    ['Log return: excess kurtosis (G2; normal = 0)', signed(summary.log_return.excess_kurtosis, 3)],
  ]
  return (
    <>
      <h2>Summary, training segment</h2>
      <div className="card scroll-x">
        <table aria-label="Training summary">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <th scope="row">{k}</th>
                <td className="num">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

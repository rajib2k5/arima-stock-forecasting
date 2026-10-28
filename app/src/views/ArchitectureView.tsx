/**
 * Architecture page: three animated diagrams (layers, the data contract, the analysis flow)
 * and the 3D wiring check. Content is static; nothing here depends on the data files.
 */
import { ActivityDiagram, ArchDiagram, SequenceDiagram, type ActEdge, type ActNode, type ArchLayer, type SeqStep } from '../lib/diagrams'
import { AicAxesPreview } from './AicAxesPreview'

const LAYERS: ArchLayer[] = [
  { label: 'Source', boxes: ['Yahoo Finance via yfinance 1.7.0 · AAPL daily'] },
  { label: 'Raw cache', boxes: ['$VOL_DATA_DIR/arima-stock-forecasting/raw/ · CSV · never committed'] },
  { label: 'Python core', boxes: ['data', 'transforms', 'stationarity', 'identification', 'models', 'evaluation'] },
  { label: 'Delivery', boxes: ['export_app_data.py → JSON', 'build_notebooks.py → .ipynb', 'reports/'] },
  { label: 'App', boxes: ['React views: read JSON only', 'src/lib: pure UI transforms'] },
]

const ACTORS = ['export_app_data', 'pipeline', 'disk', 'App', 'contract', 'View']
const STEPS: SeqStep[] = [
  { from: 0, to: 1, label: 'run' },
  { from: 1, to: 0, label: 'results' },
  { from: 0, to: 2, label: 'write meta.json (envelope)' },
  { from: 3, to: 2, label: 'fetch data/meta.json' },
  { from: 3, to: 4, label: 'parseEnvelope' },
  { from: 4, to: 3, label: 'typed data or errors' },
  { from: 3, to: 5, label: 'render' },
]

const FLOW_LABELS = [
  'fetch AAPL',
  'clean (ffill)',
  'log transform',
  'ADF + KPSS',
  'difference',
  'ACF/PACF',
  'order search (train only)',
  'fit ARIMA',
  'residual diagnostics',
  'static forecast',
  'walk-forward forecast',
  'random-walk baseline',
  'RMSE / MAE / MAPE',
  'export JSON',
]
const NODES: ActNode[] = [
  { id: 'start', label: 'start', type: 'start' },
  ...FLOW_LABELS.map((label, i) => ({ id: `n${i}`, label })),
  { id: 'end', label: 'done', type: 'end' },
]
const EDGES: ActEdge[] = NODES.slice(1).map((n, i) => ({ from: NODES[i].id, to: n.id }))

export function ArchitectureView() {
  return (
    <section className="architecture">
      <h2>Architecture</h2>
      <p className="sub">
        One direction only: a public data source feeds a Python core, the core exports versioned JSON, and the app reads that JSON.
        The app has no model code and no network calls except for its own data files.
      </p>

      <h2>Layers</h2>
      <div className="card diagram-card">
        <ArchDiagram layers={LAYERS} />
      </div>
      <dl className="layer-notes">
        <dt>Source</dt>
        <dd>Yahoo Finance through yfinance 1.7.0, AAPL daily bars.</dd>
        <dt>Raw cache</dt>
        <dd>
          CSV files in <code>$VOL_DATA_DIR/arima-stock-forecasting/raw/</code>. They live outside the repository and are never committed.
        </dd>
        <dt>Python core</dt>
        <dd>
          <code>src/arima_forecasting</code>: data, transforms, stationarity, identification, models, evaluation.
        </dd>
        <dt>Delivery</dt>
        <dd>
          <code>tools/export_app_data.py</code> writes versioned JSON into <code>app/public/data/</code>;{' '}
          <code>tools/build_notebooks.py</code> writes <code>notebooks/</code>; result tables produced by the pipeline (from milestone 4) go in <code>reports/</code>.
        </dd>
        <dt>App</dt>
        <dd>
          React views read the JSON only. <code>src/lib</code> holds the pure, unit-tested UI transforms.
        </dd>
      </dl>

      <h2>Sequence: the data contract</h2>
      <p className="sub">
        Every file is an envelope with a schema version, a UTC timestamp and the source commit. The app refuses any major version
        other than 1 and shows every problem it finds in a file instead of drawing a half-wrong page.
      </p>
      <div className="card diagram-card">
        <SequenceDiagram actors={ACTORS} steps={STEPS} />
      </div>

      <h2>Activity: the analysis flow</h2>
      <p className="sub">
        The order search runs on the training split only. The three forecasts (static, walk-forward, random walk) are scored with the
        same three metrics.
      </p>
      <div className="card diagram-card">
        <ActivityDiagram nodes={NODES} edges={EDGES} />
      </div>

      <h2>3D wiring check</h2>
      <p className="sub">
        A react-three-fiber canvas proves the 3D stack works before any data exists. Drag to rotate. It does not spin by itself if
        your system asks for reduced motion.
      </p>
      <div className="card">
        <AicAxesPreview />
      </div>
    </section>
  )
}

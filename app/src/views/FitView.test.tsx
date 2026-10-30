import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { FitPage } from './FitView'
import type { FitState } from '../data/useFitData'
import type { LoadResult } from '../data/loadArtifact'
import { parseEnvelope, type Envelope } from '../lib/contract'
import type { ArchVerdict, Fit, ModelId, NormalityVerdict, SerialVerdict } from '../lib/contract.fit'
import { ARCH_LABELS, ARCH_READINGS, NORMALITY_LABELS, NORMALITY_READINGS, SERIAL_LABELS, SERIAL_READINGS } from '../lib/fitText'
import { fitEnvelope, fixtureFit, residualsData } from '../test/fixtures/payloads'

type Residual = ReturnType<typeof residualsData> & { acf: Correlogram; acf_squared: Correlogram }
type Correlogram = { outside_count: number; rows: { acf: number; outside: boolean }[] }

function ready(edit?: (fit: Fit) => void): FitState {
  const fit = fixtureFit()
  edit?.(fit)
  return { status: 'ready', fit, envelope: fitEnvelope('fit') as Envelope }
}

/** A fake loader of the made-up residual files, each optionally edited first; it records what was asked for. */
function fakeLoad(edits: Partial<Record<ModelId, (data: Residual) => void>> = {}, failures: Record<string, LoadResult> = {}) {
  const calls: string[] = []
  const load = async (name: string): Promise<LoadResult> => {
    calls.push(name)
    if (failures[name]) return failures[name]
    const id = name.replace('residuals_', '') as ModelId
    const data = residualsData(id) as Residual
    edits[id]?.(data)
    const parsed = parseEnvelope({ ...(fitEnvelope(`residuals_${id}`) as object), data })
    if (!parsed.ok) throw new Error(parsed.errors.join('; '))
    return { ok: true, envelope: parsed.envelope }
  }
  return Object.assign(load, { calls })
}

/** A loader whose files never arrive, for tests that look only at fit.json. */
const pending = () => new Promise<LoadResult>(() => {})

const barClasses = (name: string) =>
  within(screen.getByRole('img', { name }))
    .getAllByTestId('correlogram-bar')
    .map((bar) => bar.getAttribute('class'))

describe('FitPage', () => {
  it('says it is loading fit.json', () => {
    render(<FitPage state={{ status: 'loading' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/fit.json')
  })

  it('names the failing file and says how to rebuild it', () => {
    render(<FitPage state={{ status: 'error', artifact: 'fit', error: { kind: 'contract', errors: Array.from({ length: 13 }, (_, i) => `p${i}`) } }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not load fit.json.')
    expect(within(alert).getAllByRole('listitem')).toHaveLength(12)
    expect(alert).toHaveTextContent('…and 1 more.')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
  })

  it('shows the primary model first, with its estimates, standard errors and p-values as exported', async () => {
    render(<FitPage state={ready()} load={fakeLoad()} />)
    expect(screen.getByRole('radio', { name: 'AIC choice (primary)' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByLabelText('Model summary')).toHaveTextContent('ARIMA(3, 1, 2) with a drift · AIC choice (ADR-0002)')
    const table = screen.getByRole('table', { name: "Estimates of ARIMA(3, 1, 2) with a drift, with statsmodels' standard errors (outer product of gradients)" })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getByRole('rowheader').textContent)).toEqual(['drift (statsmodels: x1)', 'ar.L1', 'ar.L2', 'ar.L3', 'ma.L1', 'ma.L2', 'sigma2'])
    // ar.L1: 0.6 with SE 0.25, so z 2.4, p 0.0164 and 0.6 ± 1.96 × 0.25, all written by the fixture's Python
    expect(within(rows[1]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['0.6000', '0.2500', '2.400', '0.016', '[0.1100, 1.090]'])
    expect(await screen.findByRole('img', { name: 'Standardised residuals of ARIMA(3, 1, 2) with a drift, 2015-01-05 to 2015-01-13' })).toBeInTheDocument()
  })

  it('writes sigma2 with its standard error and interval, and a dash with a note for its z and p-value', () => {
    render(<FitPage state={ready()} load={pending} />)
    const row = within(screen.getByRole('table', { name: /^Estimates of/ })).getAllByRole('row')[7]
    expect(within(row).getByRole('rowheader')).toHaveTextContent('sigma2')
    expect(within(row).getAllByRole('cell').map((c) => c.textContent)).toEqual(['0.0003100', '0.00005000', '—', '—†', '[0.0002120, 0.0004080]'])
    expect(screen.getByLabelText('sigma2 note')).toHaveTextContent('† sigma2 has a standard error but no z and no p-value: its null value, 0, is on the boundary')
  })

  it('sets a small p-value as a power of ten with a superscript, and one that underflowed as "< 1e-300", never "0"', () => {
    render(
      <FitPage
        state={ready((f) => {
          f.models[0].diagnostics.arch_lm[0].p_value = 2.4e-50
          f.models[0].diagnostics.jarque_bera.p_value = 0
        })}
        load={pending}
      />,
    )
    const arch = within(screen.getByRole('rowgroup', { name: 'ARCH-LM' })).getAllByRole('row')[0]
    const p = within(arch).getAllByRole('cell')[3]
    expect(p).toHaveTextContent('2.4 × 10−50')
    expect(p.querySelector('sup')?.textContent).toBe('−50')
    const jb = within(screen.getByRole('rowgroup', { name: 'Jarque–Bera' })).getAllByRole('row')[0]
    expect(within(jb).getAllByRole('cell')[3].textContent).toBe('< 1e-300')
  })

  it('writes a dash for each inference field of a parameter without a covariance', () => {
    render(
      <FitPage
        state={ready((f) => {
          Object.assign(f.models[0].params[2], { std_err: null, z: null, p_value: null, ci_low: null, ci_high: null })
        })}
        load={pending}
      />,
    )
    const row = within(screen.getByRole('table', { name: /^Estimates of/ })).getAllByRole('row')[3]
    expect(within(row).getAllByRole('cell').map((c) => c.textContent)).toEqual(['−0.2500', '—', '—', '—', '—'])
  })

  it('loads a model’s residual file only when that model is picked, and keeps it', async () => {
    const load = fakeLoad()
    render(<FitPage state={ready()} load={load} />)
    await screen.findByRole('img', { name: /^Standardised residuals of ARIMA\(3, 1, 2\)/ })
    expect(load.calls).toEqual(['residuals_aic'])
    fireEvent.click(screen.getByRole('radio', { name: 'BIC choice' }))
    expect(screen.getByRole('radio', { name: 'BIC choice' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('table', { name: /^Estimates of ARIMA\(1, 1, 0\) without a drift/ })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: /^Standardised residuals of ARIMA\(1, 1, 0\) without a drift/ })).toBeInTheDocument()
    expect(load.calls).toEqual(['residuals_aic', 'residuals_bic'])
    fireEvent.click(screen.getByRole('radio', { name: 'AIC choice (primary)' }))
    expect(screen.getByRole('img', { name: /^Standardised residuals of ARIMA\(3, 1, 2\)/ })).toBeInTheDocument()
    expect(load.calls).toEqual(['residuals_aic', 'residuals_bic'])
  })

  it('names a residual file that fails to load', async () => {
    render(<FitPage state={ready()} load={fakeLoad({}, { residuals_course: { ok: false, error: { kind: 'http', url: './data/residuals_course.json', status: 404, statusText: 'Not Found' } } })} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Course model' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load residuals_course.json.')
  })

  it('says so for a Ljung–Box lag at or below p + q, where the test is not applied', () => {
    render(<FitPage state={ready()} load={pending} />)
    const rows = within(screen.getByRole('rowgroup', { name: 'Ljung–Box' })).getAllByRole('row')
    expect(rows[0]).toHaveTextContent('not applied (lag ≤ p + q = 5)')
    expect(rows[1]).not.toHaveTextContent('not applied')
    expect(rows[2]).not.toHaveTextContent('not applied')
    expect(within(rows[1]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['10', '5.900', '5', '0.316'])
    expect(within(rows[2]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['20', '12.40', '15', '0.649'])
  })

  it('reads each test by its own exported verdict, with one verdict flipped at a time', () => {
    // A reading wired to another test's verdict fails here: only one verdict differs from the base.
    const groups = { serial_correlation: 'Ljung–Box', normality: 'Jarque–Bera', arch: 'ARCH-LM' } as const
    const base = { serial_correlation: 'not_found', normality: 'rejected', arch: 'found' } as const
    const flips = [{ serial_correlation: 'found' }, { normality: 'not_rejected' }, { arch: 'not_found' }, { serial_correlation: 'not_tested' }] as const
    for (const flip of [{}, ...flips]) {
      const v: { serial_correlation: SerialVerdict; normality: NormalityVerdict; arch: ArchVerdict } = { ...base, ...flip }
      const { unmount } = render(<FitPage state={ready((f) => (f.models[0].diagnostics.verdicts = v))} load={pending} />)
      const group = (k: keyof typeof groups) => screen.getByRole('rowgroup', { name: groups[k] })
      const expected = {
        serial_correlation: [SERIAL_LABELS, SERIAL_READINGS, v.serial_correlation === 'found'] as const,
        normality: [NORMALITY_LABELS, NORMALITY_READINGS, v.normality === 'rejected'] as const,
        arch: [ARCH_LABELS, ARCH_READINGS, v.arch === 'found'] as const,
      }
      for (const k of Object.keys(groups) as (keyof typeof groups)[]) {
        const [labels, readings, flagged] = expected[k]
        const verdict = v[k] as keyof typeof labels & keyof typeof readings
        expect(group(k)).toHaveTextContent(readings[verdict])
        for (const other of Object.keys(readings).filter((o) => o !== verdict)) expect(group(k)).not.toHaveTextContent(readings[other as keyof typeof readings])
        // The badge: its words, and its colour class (flag for a rejection, plain otherwise).
        const badge = within(group(k)).getByText(labels[verdict])
        expect(badge).toHaveClass('verdict', flagged ? 'verdict-flag' : 'verdict-plain')
        expect(badge).not.toHaveClass(flagged ? 'verdict-plain' : 'verdict-flag')
      }
      unmount()
    }
  })

  it('reads each test by the verdict Python exported, not by its p-values', () => {
    const { unmount } = render(<FitPage state={ready()} load={pending} />)
    const lb = () => screen.getByRole('rowgroup', { name: 'Ljung–Box' })
    const arch = () => screen.getByRole('rowgroup', { name: 'ARCH-LM' })
    expect(lb()).toHaveTextContent('no autocorrelation is left')
    expect(lb()).toHaveTextContent('0.316')
    expect(arch()).toHaveTextContent('large residuals cluster in time')
    expect(screen.getByRole('rowgroup', { name: 'Jarque–Bera' })).toHaveTextContent('Jarque–Bera rejects normality')
    unmount()
    // The same p-values, the verdicts flipped: the readings follow the verdicts.
    render(
      <FitPage
        state={ready((f) => {
          f.models[0].diagnostics.verdicts = { serial_correlation: 'found', normality: 'not_rejected', arch: 'not_found' }
        })}
        load={pending}
      />,
    )
    expect(lb()).toHaveTextContent('still carry autocorrelation')
    expect(lb()).not.toHaveTextContent('no autocorrelation is left')
    expect(lb()).toHaveTextContent('0.316')
    expect(arch()).toHaveTextContent('no volatility clustering is detected')
    expect(screen.getByRole('rowgroup', { name: 'Jarque–Bera' })).toHaveTextContent('Jarque–Bera does not reject normality')
  })

  it('reads a model with no applied Ljung–Box lag as not tested', () => {
    render(
      <FitPage
        state={ready((f) => {
          f.models[0].diagnostics.verdicts.serial_correlation = 'not_tested'
        })}
        load={pending}
      />,
    )
    expect(screen.getByRole('rowgroup', { name: 'Ljung–Box' })).toHaveTextContent('Not tested')
    expect(screen.getByRole('rowgroup', { name: 'Ljung–Box' })).toHaveTextContent('No Ljung–Box lag is above p + q, so the test was applied at no lag')
  })

  it('draws an ACF bar as past the band exactly when Python flagged it', async () => {
    const load = fakeLoad({
      aic: (d) => {
        d.acf.rows[0].outside = true // an acf of 0.1, well inside the band of 0.74: flagged anyway
        d.acf.outside_count = 1
        d.acf_squared.rows[0].outside = false // 0.8, past the band: not flagged
        d.acf_squared.outside_count = 0
      },
    })
    render(<FitPage state={ready()} load={load} />)
    await screen.findByRole('img', { name: 'ACF of the standardised residuals, lags 1 to 3' })
    expect(barClasses('ACF of the standardised residuals, lags 1 to 3')).toEqual(['bar outside', 'bar', 'bar'])
    expect(barClasses('ACF of the squared standardised residuals, lags 1 to 3')).toEqual(['bar', 'bar', 'bar'])
  })

  it('draws the exported flags of the base file', async () => {
    render(<FitPage state={ready()} load={fakeLoad()} />)
    await screen.findByRole('img', { name: 'ACF of the squared standardised residuals, lags 1 to 3' })
    expect(barClasses('ACF of the standardised residuals, lags 1 to 3')).toEqual(['bar', 'bar', 'bar'])
    expect(barClasses('ACF of the squared standardised residuals, lags 1 to 3')).toEqual(['bar outside', 'bar', 'bar'])
    expect(screen.getByRole('img', { name: /^QQ plot/ })).toBeInTheDocument()
  })

  it('marks the cancelling pairs Python exported, and only those', () => {
    const circle = () => screen.getByRole('img', { name: /^Inverse roots of/ })
    const first = render(<FitPage state={ready()} load={pending} />)
    expect(circle()).toHaveAccessibleName('Inverse roots of ARIMA(3, 1, 2) with a drift on the unit circle: 3 AR, 2 MA, 2 cancelling pairs')
    expect(within(circle()).getAllByTestId('root-ar')).toHaveLength(3)
    expect(within(circle()).getAllByTestId('root-ma')).toHaveLength(2)
    expect(within(circle()).getAllByTestId('root-pair')).toHaveLength(2)
    expect(screen.getAllByTestId('pair-item').map((li) => li.textContent)).toEqual([
      'AR root 1 (0.300 − 0.400i) and MA root 1 (0.320 − 0.370i): 0.0361 apart, within 0.1',
      'AR root 2 (0.300 + 0.400i) and MA root 2 (0.320 + 0.370i): 0.0361 apart, within 0.1',
    ])
    first.unmount()
    // The same close roots, no exported pairs: nothing is marked.
    const none = render(<FitPage state={ready((f) => (f.models[0].cancelling_pairs = []))} load={pending} />)
    expect(within(circle()).queryAllByTestId('root-pair')).toHaveLength(0)
    expect(screen.getByText(/^No cancelling pairs/)).toBeInTheDocument()
    none.unmount()
    render(<FitPage state={ready((f) => (f.models[0].cancelling_pairs = [{ ar: 1, ma: 1, distance: 0.0361 }]))} load={pending} />)
    expect(within(circle()).getAllByTestId('root-pair')).toHaveLength(1)
    expect(screen.getAllByTestId('pair-item')[0]).toHaveTextContent(/^AR root 2 .* MA root 2/)
  })

  it('sizes the legend icons and caps the QQ plot on the elements themselves, which no stylesheet rule outranks', async () => {
    // `.plot svg` is 100% wide: in a browser the icons drew at 300 px and the QQ drawing at the card's width.
    const { container } = render(<FitPage state={ready()} load={fakeLoad()} />)
    const marks = Array.from(container.querySelectorAll<SVGSVGElement>('svg.legend-mark'))
    expect(marks).toHaveLength(3)
    for (const mark of marks) {
      expect([mark.getAttribute('width'), mark.getAttribute('height')]).toEqual(['12', '12'])
      expect([mark.style.width, mark.style.height]).toEqual(['12px', '12px'])
    }
    await screen.findByRole('img', { name: /^QQ plot/ })
    const qq = container.querySelector<HTMLDivElement>('.qq-plot')
    expect(qq?.style.maxWidth).toBe('560px')
    expect(qq).toContainElement(screen.getByRole('img', { name: /^QQ plot/ }))
  })

  it('shows the clustering prediction and the burned residual, as exported', () => {
    render(<FitPage state={ready()} load={pending} />)
    const cp = screen.getByLabelText('Clustering prediction')
    expect(cp).toHaveTextContent('Confirmed: the residuals of the primary model show volatility clustering')
    expect(cp).toHaveTextContent('ARCH-LM rejects at 2 of 2 lags; 1 of 50 squared-residual ACF bars lie past their band, against 2.50 expected by chance')
    const burned = screen.getByLabelText('Burned residuals')
    expect(burned).toHaveTextContent('the residual of 2015-01-02 out of the likelihood and these tests: it is 0.0310 log points')
    expect(burned).toHaveTextContent("a largest |residual| of 0.0210 after the burn-in. The course's plots include this first residual.")
  })

  it('shows the course’s recipe: the two searches, the test rows seen, the dropped drift', () => {
    render(<FitPage state={ready()} load={pending} />)
    const track = screen.getByLabelText('Course track')
    expect(track).toHaveTextContent('on the training split alone it chose the same order and intercept, ARIMA(0, 1, 1) with a drift')
    expect(track).toHaveTextContent('on the full series of 42 rows, not on the 40 rows of the training split, so its search saw 2 test rows')
    expect(track).toHaveTextContent('auto_arima picked trend t')
    expect(track).toHaveTextContent('(without − with = 1.500); the drift is 0.000900 log points per day, SE 0.000400, p-value 0.024')
  })

  it('names the provenance of both files', async () => {
    render(<FitPage state={ready()} load={fakeLoad()} />)
    await screen.findByRole('img', { name: /^Standardised residuals/ })
    expect(screen.getByLabelText('Fit provenance')).toHaveTextContent('fit: commit ddddddd · residuals_aic: commit ddddddd · 40 rows of training data')
  })
})

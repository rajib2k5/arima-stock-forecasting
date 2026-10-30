import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { ForecastPage } from './ForecastView'
import type { EvaluationState } from '../data/useForecastData'
import type { LoadResult } from '../data/loadArtifact'
import { parseEnvelope, type Envelope } from '../lib/contract'
import { COVERAGE_VERDICTS, DM_VERDICTS, type CoverageVerdict, type DmVerdict, type Evaluation } from '../lib/contract.forecast'
import { COVERAGE_LABELS, COVERAGE_READINGS, DM_LABELS, DM_READINGS, DM_STATIC_NOTE } from '../lib/forecastText'
import { fixtureEvaluation, forecastEnvelope } from '../test/fixtures/payloads'

function ready(edit?: (e: Evaluation) => void): EvaluationState {
  const evaluation = fixtureEvaluation()
  edit?.(evaluation)
  return { status: 'ready', evaluation, envelope: forecastEnvelope('evaluation') as Envelope }
}

/** A fake loader of the made-up forecast files, each optionally edited first; it records what was asked for. */
function fakeLoad(failures: Record<string, LoadResult> = {}, edit?: (name: string, data: { windows: { rows: Record<string, number>[] }[] }) => void) {
  const calls: string[] = []
  const load = async (name: string): Promise<LoadResult> => {
    calls.push(name)
    if (failures[name]) return failures[name]
    const envelope = forecastEnvelope(name) as { data: { windows: { rows: Record<string, number>[] }[] } }
    edit?.(name, envelope.data)
    const parsed = parseEnvelope(envelope)
    if (!parsed.ok) throw new Error(parsed.errors.join('; '))
    return { ok: true, envelope: parsed.envelope }
  }
  return Object.assign(load, { calls })
}

/** A loader whose files never arrive, for tests that look only at evaluation.json. */
const pending = () => new Promise<LoadResult>(() => {})

const radio = (group: string, name: string | RegExp) => within(screen.getByRole('radiogroup', { name: group })).getByRole('radio', { name })
const fan = () => screen.findByTestId('fan-chart')
const status = () => screen.getByTestId('walk-status').textContent ?? ''
const button = (name: string) => screen.getByRole('button', { name })

/** The [x, y] points of an SVG path's d attribute (its M and L commands; Z has no numbers). */
function pointsOf(testIdOrElement: string | Element): [number, number][] {
  const el = typeof testIdOrElement === 'string' ? screen.getByTestId(testIdOrElement) : testIdOrElement
  const nums = (el.getAttribute('d') ?? '').match(/-?\d+(\.\d+)?/g)?.map(Number) ?? []
  return nums.flatMap((v, k) => (k % 2 === 0 ? [[v, nums[k + 1]] as [number, number]] : []))
}
/** A ribbon's points split into its upper edge (left to right) and its lower edge (right to left), as drawn. */
function edges(testIdOrElement: string | Element): { upper: [number, number][]; lower: [number, number][] } {
  const pts = pointsOf(testIdOrElement)
  return { upper: pts.slice(0, pts.length / 2), lower: pts.slice(pts.length / 2) }
}
/** A raw coordinate against a path's, which the chart writes to one decimal. */
const near = (raw: string | null, written: number) => expect(Math.abs(Number(raw) - written)).toBeLessThanOrEqual(0.051)

/** The badge colour each verdict takes on the page (DM_TONE and COVERAGE_TONE in ForecastView.tsx, as the fit page's). */
const DM_TONES: Record<DmVerdict, string> = { beats_rw: 'plain', no_difference: 'inconclusive', worse_than_rw: 'flag', same_as_rw: 'inconclusive' }
const COVERAGE_TONES: Record<CoverageVerdict, string> = { too_narrow: 'flag', consistent: 'plain', too_wide: 'flag', not_tested: 'inconclusive' }

/** The page on the aic walk-forward test window, its file loaded. */
async function walkForward(options: { reduced?: boolean; state?: EvaluationState } = {}) {
  const view = render(<ForecastPage state={options.state ?? ready()} load={fakeLoad()} readReducedMotion={() => options.reduced ?? false} />)
  fireEvent.click(radio('Method', 'Walk-forward one-step'))
  await screen.findByTestId('walk-chart')
  return view
}

afterEach(() => {
  vi.useRealTimers()
})

describe('ForecastPage', () => {
  it('says it is loading evaluation.json', () => {
    render(<ForecastPage state={{ status: 'loading' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/evaluation.json')
  })

  it('names the failing file and says how to rebuild it', () => {
    render(<ForecastPage state={{ status: 'error', artifact: 'evaluation', error: { kind: 'contract', errors: Array.from({ length: 13 }, (_, i) => `p${i}`) } }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not load evaluation.json.')
    expect(within(alert).getAllByRole('listitem')).toHaveLength(12)
    expect(alert).toHaveTextContent('…and 1 more.')
    expect(within(alert).getByText('uv run python tools/export_app_data.py')).toBeInTheDocument()
  })

  it('opens on the AIC model’s static forecast of the test window, with the labels evaluation.json gives', async () => {
    const load = fakeLoad()
    render(<ForecastPage state={ready()} load={load} />)
    expect(radio('Model', 'AIC choice (ADR-0002)')).toHaveAttribute('aria-checked', 'true')
    expect(radio('Method', "Static multi-step (the course's)")).toHaveAttribute('aria-checked', 'true')
    expect(radio('Window', 'Test, 2021-06-21 to 2021-06-25')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('status')).toHaveTextContent('Loading data/forecast_aic_static.json')
    expect(await fan()).toHaveAccessibleName(
      "Forecast of AIC choice (ADR-0002), Static multi-step (the course's), test window 2021-06-21 to 2021-06-25: actual and median price in dollars, with the 80% and 95% normal intervals",
    )
    expect(load.calls).toEqual(['forecast_aic_static'])
    expect(screen.getByLabelText('Forecast provenance')).toHaveTextContent('evaluation: commit eeeeeee · forecast_aic_static: commit eeeeeee')
  })

  it('offers the refit only where evaluation.json lists it: the AIC model', async () => {
    const load = fakeLoad()
    render(<ForecastPage state={ready()} load={load} />)
    const methods = () => within(screen.getByRole('radiogroup', { name: 'Method' })).getAllByRole('radio').map((r) => r.textContent)
    expect(methods()).toEqual(["Static multi-step (the course's)", 'Walk-forward one-step', 'Walk-forward one-step, refit every 21 days'])
    fireEvent.click(radio('Method', 'Walk-forward one-step, refit every 21 days'))
    await screen.findByRole('img', { name: /^Forecast of AIC choice \(ADR-0002\), Walk-forward one-step, refit every 21 days/ })
    fireEvent.click(radio('Model', 'BIC choice'))
    expect(methods()).toEqual(["Static multi-step (the course's)", 'Walk-forward one-step'])
    // The refit picked on the AIC model shows the walk-forward on a model without one.
    expect(radio('Method', 'Walk-forward one-step')).toHaveAttribute('aria-checked', 'true')
    await screen.findByRole('img', { name: /^Forecast of BIC choice, Walk-forward one-step, test window/ })
    fireEvent.click(radio('Model', 'Course refit'))
    expect(methods()).toEqual(["Static multi-step (the course's)", 'Walk-forward one-step'])
    await screen.findByRole('img', { name: /^Forecast of Course refit, Walk-forward one-step/ })
    expect(load.calls).toEqual(['forecast_aic_static', 'forecast_aic_refit', 'forecast_bic_walk_forward', 'forecast_course_walk_forward'])
  })

  it('fetches a forecast file only when its pair is picked, and keeps it; the window needs no fetch', async () => {
    const load = fakeLoad()
    render(<ForecastPage state={ready()} load={load} />)
    await fan()
    fireEvent.click(radio('Window', 'Out of sample, 2021-06-28 to 2021-07-23'))
    expect(await fan()).toHaveAccessibleName(/out of sample window 2021-06-28 to 2021-07-23/)
    fireEvent.click(radio('Method', 'Walk-forward one-step'))
    await screen.findByTestId('walk-chart')
    fireEvent.click(radio('Method', "Static multi-step (the course's)"))
    expect(screen.getByTestId('fan-chart')).toHaveAccessibleName(/^Forecast of AIC choice \(ADR-0002\), Static multi-step/)
    expect(load.calls).toEqual(['forecast_aic_static', 'forecast_aic_walk_forward'])
  })

  it('names a forecast file that fails to load', async () => {
    render(<ForecastPage state={ready()} load={fakeLoad({ forecast_aic_static: { ok: false, error: { kind: 'http', url: './data/forecast_aic_static.json', status: 404, statusText: 'Not Found' } } })} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load forecast_aic_static.json.')
  })

  it('draws the static random walk at the origin’s price for the static method only', async () => {
    render(<ForecastPage state={ready()} load={fakeLoad()} />)
    await fan()
    expect(screen.getByTestId('rw-line')).toBeInTheDocument()
    expect(screen.getByText("Random walk: the origin's price, $36.62 on 2021-06-18")).toBeInTheDocument()
    fireEvent.click(radio('Method', 'Walk-forward one-step'))
    await screen.findByTestId('walk-chart')
    expect(screen.queryByTestId('rw-line')).toBeNull()
  })

  it('labels the 80% and 95% bands on the bands they name, the 80% inside the 95%', async () => {
    render(<ForecastPage state={ready()} load={fakeLoad()} />)
    await fan()
    const legend = (level: string) => screen.getAllByRole('listitem').find((li) => li.textContent?.startsWith(`${level}% interval`))
    expect(legend('80')?.querySelector('svg.legend-mark rect')).toHaveClass('fan-band80')
    expect(legend('95')?.querySelector('svg.legend-mark rect')).toHaveClass('fan-band95')
    // The y values of a ribbon's path: every second number after the M and L commands.
    const ys = (testId: string) => (screen.getByTestId(testId).getAttribute('d') ?? '').match(/-?\d+(\.\d+)?/g)!.map(Number).filter((_, k) => k % 2 === 1)
    expect(screen.getByTestId('band-80')).toHaveClass('fan-band80')
    expect(screen.getByTestId('band-95')).toHaveClass('fan-band95')
    expect(Math.min(...ys('band-95'))).toBeLessThan(Math.min(...ys('band-80')))
    expect(Math.max(...ys('band-95'))).toBeGreaterThan(Math.max(...ys('band-80')))
  })

  it('shows the mean only when asked, and switches the bands to the Student-t ones', async () => {
    render(<ForecastPage state={ready()} load={fakeLoad()} />)
    await fan()
    expect(screen.queryByTestId('mean-line')).toBeNull()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show the mean, exp(μ + s²/2)' }))
    expect(screen.getByTestId('mean-line')).toBeInTheDocument()
    expect(screen.getByText('Mean exp(μ + s²/2)')).toBeInTheDocument()
    const normal80 = screen.getByTestId('band-80').getAttribute('d')
    const normal95 = screen.getByTestId('band-95').getAttribute('d')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Student-t bands (variance-matched) instead of normal' }))
    expect(screen.getByTestId('fan-chart')).toHaveAccessibleName(/with the 80% and 95% Student-t \(variance-matched\) intervals$/)
    expect(screen.getByTestId('band-80').getAttribute('d')).not.toBe(normal80)
    expect(screen.getByTestId('band-95').getAttribute('d')).not.toBe(normal95)
    expect(screen.getByText('80% interval (Student-t (variance-matched))')).toBeInTheDocument()
  })

  it('draws each Student-t bound from its own exported field, each one at a time', async () => {
    // Each t bound of the static file set onto a line the chart draws anyway (the reader re-checks no dollar
    // value, ADR-0001): the 95% upper onto the actual price, the 95% lower onto the median, the 80% upper onto
    // the mean and the 80% lower onto the origin's price (the static random walk's line). So a bound taken
    // from another field (the normal one, say) leaves its line.
    render(
      <ForecastPage
        state={ready()}
        load={fakeLoad({}, (name, data) => {
          if (name !== 'forecast_aic_static') return
          const origin = (data.windows[0] as unknown as { origin: { close_usd: number } }).origin.close_usd
          data.windows[0].rows.forEach((r) => Object.assign(r, { t_upper_95_usd: r.actual_usd, t_lower_95_usd: r.median_usd, t_upper_80_usd: r.mean_usd, t_lower_80_usd: origin }))
        })}
      />,
    )
    await fan()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show the mean, exp(μ + s²/2)' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Student-t bands (variance-matched) instead of normal' }))
    const reversed = (pts: [number, number][]) => [...pts].reverse()
    expect(edges('band-95').upper).toEqual(pointsOf('actual-line'))
    expect(reversed(edges('band-95').lower)).toEqual(pointsOf('median-line'))
    expect(edges('band-80').upper).toEqual(pointsOf('mean-line'))
    const rwY = Number(screen.getByTestId('rw-line').getAttribute('y1'))
    for (const [, y] of edges('band-80').lower) near(String(rwY), y)
    // The normal bands are back when the box is cleared: none of them on those lines.
    fireEvent.click(screen.getByRole('checkbox', { name: 'Student-t bands (variance-matched) instead of normal' }))
    expect(edges('band-95').upper).not.toEqual(pointsOf('actual-line'))
  })

  it('draws the mean line through the exported mean_usd, not the median', async () => {
    // mean_usd set to the day's actual price (the reader re-checks no dollar value, ADR-0001): the mean line
    // must then lie exactly on the actual line, and off the median line.
    render(<ForecastPage state={ready()} load={fakeLoad({}, (_name, data) => data.windows.forEach((w) => w.rows.forEach((r) => (r.mean_usd = r.actual_usd))))} />)
    await fan()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show the mean, exp(μ + s²/2)' }))
    expect(pointsOf('mean-line')).toEqual(pointsOf('actual-line'))
    expect(pointsOf('mean-line')).not.toEqual(pointsOf('median-line'))
    expect(pointsOf('mean-line')).toHaveLength(5)
  })

  it('places the prices on a log axis when asked, with ticks at round dollar values', async () => {
    // A wide 95% band on the last test day, as on the real static oos path: up to $800.
    const wide = fakeLoad({}, (name, data) => {
      if (name === 'forecast_aic_static') Object.assign(data.windows[0].rows[4], { lower_95_usd: 120, upper_95_usd: 800 })
    })
    render(<ForecastPage state={ready()} load={wide} />)
    await fan()
    const ticks = () => Array.from(screen.getByTestId('fan-chart').querySelectorAll('g.tick text')).map((el) => [el.textContent ?? '', Number(el.getAttribute('y'))] as const)
    expect(ticks().map(([label]) => label)).toEqual(['200', '400', '600', '800'])
    expect(screen.getByTestId('y-label')).toHaveTextContent(/^dollars \(adjusted close\)$/)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Log price axis (forecast chart)' }))
    expect(screen.getByTestId('fan-chart')).toHaveAccessibleName(/, on a log price axis$/)
    expect(screen.getByTestId('y-label')).toHaveTextContent('dollars (adjusted close), log scale')
    const y = Object.fromEntries(ticks())
    // The other days sit near $35, so the axis runs from about $29 to $900: 1, 2 and 5 times powers of ten.
    expect(Object.keys(y)).toEqual(['50', '100', '200', '500'])
    // Equal ratios take equal heights (50 to 100, 100 to 200); on the linear axis the second gap is twice the first.
    expect(y['50'] - y['100']).toBeCloseTo(y['100'] - y['200'], 6)
    expect((y['200'] - y['500']) / (y['100'] - y['200'])).toBeCloseTo(Math.log(2.5) / Math.log(2), 6)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Log price axis (forecast chart)' }))
    expect(ticks().map(([label]) => label)).toEqual(['200', '400', '600', '800'])
  })

  it('gives the chart, the animation and every legend mark an explicit size, and the chart a viewBox', async () => {
    // A legend icon without width and height drew at 300 px in a browser on the fit page; jsdom cannot see that, the attributes can.
    const { container } = await walkForward()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show the mean, exp(μ + s²/2)' }))
    for (const id of ['fan-chart', 'walk-chart']) {
      const svg = screen.getByTestId(id)
      expect([svg.getAttribute('width'), svg.getAttribute('height'), svg.getAttribute('viewBox')]).toEqual(['720', '300', '0 0 720 300'])
    }
    const marks = Array.from(container.querySelectorAll<SVGSVGElement>('svg.legend-mark'))
    expect(marks).toHaveLength(8) // actual, median, mean, 80%, 95%; actual, that day, earlier days
    for (const mark of marks) {
      expect([mark.getAttribute('width'), mark.getAttribute('height'), mark.getAttribute('viewBox')]).toEqual(['12', '12', '0 0 12 12'])
      expect([mark.style.width, mark.style.height]).toEqual(['12px', '12px'])
    }
    expect(container.querySelectorAll('svg:not([width])')).toHaveLength(0)
  })

  it('shows the errors of the picked forecast beside the random walk of the same kind and window, as exported', async () => {
    render(<ForecastPage state={ready()} load={pending} />)
    const cells = () =>
      within(screen.getByRole('table', { name: /^Errors of/ }))
        .getAllByRole('row')
        .slice(1)
        .map((r) => [within(r).getByRole('rowheader').textContent, ...within(r).getAllByRole('cell').map((c) => c.textContent)])
    expect(screen.getByRole('table', { name: /^Errors of/ })).toHaveAccessibleName(
      "Errors of AIC choice (ADR-0002), Static multi-step (the course's), on the test window (5 days), beside the random walk (static: the origin's price every day)",
    )
    expect(cells()[0]).toEqual(['RMSE, dollars, of the median', '$2.33', '$1.91', '1.223'])
    fireEvent.click(radio('Method', 'Walk-forward one-step'))
    expect(cells()).toEqual([
      ['RMSE, dollars, of the median', '$0.91', '$0.82', '1.114'],
      ['MAE, dollars, of the median', '$0.60', '$0.52', '1.150'],
      ['MAPE, of the median', '1.72%', '1.50%', '1.150'],
      ['RMSE, dollars, of the mean', '$0.92', '$0.82', '1.118'],
      ['MAE, dollars, of the mean', '$0.60', '$0.52', '1.153'],
      ['MAPE, of the mean', '1.73%', '1.50%', '1.153'],
      ['RMSE, log points', '0.0256', '0.0230', '1.112'],
      ['MAE, log points', '0.0169', '0.0147', '1.149'],
    ])
    expect(screen.getByLabelText('Back-transform')).toHaveTextContent('above the median exp(μ) by up to 0.018% on this window (0.018% on average)')
  })

  it('does not run the DM test for the static method, and shows one row per loss for a one-step method', () => {
    render(<ForecastPage state={ready()} load={pending} />)
    expect(screen.queryByRole('table', { name: 'Diebold–Mariano test' })).toBeNull()
    expect(screen.getByLabelText('Diebold–Mariano test')).toHaveTextContent(DM_STATIC_NOTE)
    fireEvent.click(radio('Method', 'Walk-forward one-step'))
    const table = screen.getByRole('table', { name: 'Diebold–Mariano test' })
    const squared = within(table).getByRole('rowgroup', { name: 'Squared error' })
    expect(within(squared).getAllByRole('row')[0].textContent).toBe('Squared error0.0001251.30140.263')
    expect(within(table).getByRole('rowgroup', { name: 'Absolute error' })).toBeInTheDocument()
    expect(screen.queryByText(DM_STATIC_NOTE)).toBeNull()
  })

  describe('shows the row of the picked model, method and window, and no other', () => {
    /** A number in every row that no other row has: row i of each table is told apart by i. */
    const distinct = (e: Evaluation) => {
      e.metrics.forEach((m, i) => {
        m.usd_median.rmse = i + 0.5
        m.ratio_to_rw.usd_median.rmse = i + 0.25
        m.back_transform.max_pct = i + 0.125
      })
      e.random_walk.forEach((rw, j) => (rw.usd.rmse = 50 + j))
      e.dm.forEach((d, i) => Object.assign(d, { statistic_hln: 10 + i, p_value: (i + 1) / 100 }))
      e.coverage.forEach((c, i) => Object.assign(c, { rate: (i + 1) / 100, lr: c.lr === null ? null : i + 0.5 }))
    }
    // Indices by the contract's order: metrics by FORECASTS then window; random walk multi_step test, oos, one_step test, oos;
    // DM one-step files by window then loss; coverage by file, window, distribution, level.
    const CASES = [
      { model: 'AIC choice (ADR-0002)', method: 'Walk-forward one-step, refit every 21 days', window: 'Out of sample', metric: ['$5.50', '$53.00', '5.250'], back: '5.125%', dm: [['16.00', '0.070'], ['17.00', '0.080']], cov: [['21.0%', '20.50'], ['22.0%', '21.50'], ['23.0%', '22.50'], ['24.0%', '23.50']] },
      { model: 'BIC choice', method: 'Walk-forward one-step', window: 'Out of sample', metric: ['$9.50', '$53.00', '9.250'], back: '9.125%', dm: [['20.00', '0.110'], ['21.00', '0.120']], cov: [['37.0%', '36.50'], ['38.0%', '37.50'], ['39.0%', '38.50'], ['40.0%', '39.50']] },
      { model: 'Course refit', method: "Static multi-step (the course's)", window: 'Out of sample', metric: ['$11.50', '$51.00', '11.250'], back: '11.125%', dm: null, cov: [['45.0%', '—'], ['46.0%', '—'], ['47.0%', '—'], ['48.0%', '—']] },
      { model: 'Course refit', method: 'Walk-forward one-step', window: 'Test', metric: ['$12.50', '$52.00', '12.250'], back: '12.125%', dm: [['22.00', '0.130'], ['23.00', '0.140']], cov: [['49.0%', '48.50'], ['50.0%', '49.50'], ['51.0%', '50.50'], ['52.0%', '51.50']] },
    ]
    it.each(CASES.map((c) => [`${c.model}, ${c.method}, ${c.window}`, c] as const))('%s', (_name, c) => {
      render(<ForecastPage state={ready(distinct)} load={pending} />)
      fireEvent.click(radio('Model', c.model))
      fireEvent.click(radio('Method', c.method))
      fireEvent.click(radio('Window', new RegExp(`^${c.window}`)))
      const metrics = within(screen.getByRole('table', { name: /^Errors of/ })).getAllByRole('row')[1]
      expect(within(metrics).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(c.metric)
      expect(screen.getByLabelText('Back-transform')).toHaveTextContent(`by up to ${c.back} on this window`)
      if (c.dm === null) expect(screen.queryByRole('table', { name: 'Diebold–Mariano test' })).toBeNull()
      else {
        const rows = ['Squared error', 'Absolute error'].map((name) => within(screen.getByRole('rowgroup', { name })).getAllByRole('row')[0])
        expect(rows.map((r) => within(r).getAllByRole('cell').map((cell) => cell.textContent)).map(([, stat, , p]) => [stat, p])).toEqual(c.dm)
      }
      const coverage = within(screen.getByRole('table', { name: 'Interval coverage' })).getAllByRole('rowgroup').slice(1)
      expect(coverage.map((g) => within(g).getAllByRole('row')[0]).map((r) => within(r).getAllByRole('cell')).map(([, inside, lr]) => [inside.textContent?.match(/\((.*)\)/)?.[1], lr.textContent])).toEqual(c.cov)
    })
  })

  it('reads each DM row by its own exported verdict, with one verdict flipped at a time', () => {
    for (const verdict of DM_VERDICTS) {
      // Only the squared-loss row of the test window changes; the absolute-loss row keeps the base's no_difference.
      const { unmount } = render(<ForecastPage state={ready((e) => (e.dm[0].verdict = verdict))} load={pending} />)
      fireEvent.click(radio('Method', 'Walk-forward one-step'))
      const group = (name: string) => screen.getByRole('rowgroup', { name })
      const expectReading = (name: string, v: DmVerdict) => {
        expect(group(name)).toHaveTextContent(DM_READINGS[v])
        for (const other of DM_VERDICTS.filter((o) => o !== v)) expect(group(name)).not.toHaveTextContent(DM_READINGS[other])
        expect(within(group(name)).getByText(DM_LABELS[v])).toHaveClass('verdict', `verdict-${DM_TONES[v]}`)
      }
      expectReading('Squared error', verdict)
      expectReading('Absolute error', 'no_difference')
      unmount()
    }
  })

  it('reads each coverage row by its own exported verdict, with one verdict flipped at a time', () => {
    for (const verdict of COVERAGE_VERDICTS) {
      // coverage[8] is the AIC walk-forward test window's normal 80% row; the other three stay "consistent".
      const { unmount } = render(<ForecastPage state={ready((e) => (e.coverage[8].verdict = verdict))} load={pending} />)
      fireEvent.click(radio('Method', 'Walk-forward one-step'))
      const group = (name: string) => screen.getByRole('rowgroup', { name })
      const expectReading = (name: string, v: CoverageVerdict) => {
        expect(group(name)).toHaveTextContent(COVERAGE_READINGS[v])
        for (const other of COVERAGE_VERDICTS.filter((o) => o !== v)) expect(group(name)).not.toHaveTextContent(COVERAGE_READINGS[other])
        expect(within(group(name)).getByText(COVERAGE_LABELS[v])).toHaveClass('verdict', `verdict-${COVERAGE_TONES[v]}`)
      }
      expectReading('Normal, 80%', verdict)
      for (const name of ['Normal, 95%', 'Student-t (variance-matched), 80%', 'Student-t (variance-matched), 95%']) expectReading(name, 'consistent')
      unmount()
    }
  })

  it('shows a dash for the statistic and p-value of a model that is the random walk, and says it was not tested', () => {
    const same = { verdict: 'same_as_rw', max_forecast_gap: 0, mean_diff: 0, var_diff: 0, statistic: null, statistic_hln: null, p_value: null } as const
    render(<ForecastPage state={ready((e) => Object.assign(e.dm[0], same))} load={pending} />)
    fireEvent.click(radio('Method', 'Walk-forward one-step'))
    const squared = screen.getByRole('rowgroup', { name: 'Squared error' })
    expect(within(squared).getAllByRole('row')[0].textContent).toBe('Squared error0.00—4—')
    expect(squared).toHaveTextContent(DM_READINGS.same_as_rw)
    expect(within(squared).getByText('Same as the random walk')).toHaveClass('verdict', 'verdict-inconclusive')
    expect(screen.getByRole('rowgroup', { name: 'Absolute error' })).toHaveTextContent(DM_READINGS.no_difference)
  })

  it('reads a static path’s coverage as not tested, with the count as exported', () => {
    render(<ForecastPage state={ready()} load={pending} />)
    const rows = within(screen.getByRole('table', { name: 'Interval coverage' })).getAllByRole('rowgroup').slice(1)
    expect(rows.map((g) => g.getAttribute('aria-label'))).toEqual(['Normal, 80%', 'Normal, 95%', 'Student-t (variance-matched), 80%', 'Student-t (variance-matched), 95%'])
    expect(within(rows[1]).getAllByRole('row')[0].textContent).toBe('Normal, 95%95%4 of 5 (80.0%)——')
    for (const g of rows) expect(g).toHaveTextContent(COVERAGE_READINGS.not_tested)
  })

  it('reads the coverage by the exported verdict, not by the count', () => {
    // The base row has 4 of 5 inside at 80% and reads "consistent"; the same count read "too_wide" shows that reading.
    render(<ForecastPage state={ready((e) => (e.coverage[8].verdict = 'too_wide'))} load={pending} />)
    fireEvent.click(radio('Method', 'Walk-forward one-step'))
    const row = screen.getByRole('rowgroup', { name: 'Normal, 80%' })
    expect(row).toHaveTextContent('4 of 5 (80.0%)')
    expect(row).toHaveTextContent(COVERAGE_READINGS.too_wide)
  })

  it('shows no walk-forward animation for the static method', async () => {
    render(<ForecastPage state={ready()} load={fakeLoad()} />)
    await fan()
    expect(screen.queryByTestId('walk-chart')).toBeNull()
    expect(screen.getByText(/The walk-forward animation is for the one-step methods/)).toBeInTheDocument()
  })
})

describe('the walk-forward animation', () => {
  it('starts paused on the first day, and never plays by itself', async () => {
    await walkForward()
    vi.useFakeTimers()
    expect(screen.getByTestId('walk-status')).toHaveAttribute('aria-live', 'polite')
    expect(button('Play')).not.toHaveAttribute('aria-pressed')
    expect(status()).toBe(
      'Day 1 of 5, 2021-06-21. Forecast made the evening before: median $36.80, 80% $35.92 to $37.71, 95% $35.46 to $38.20. Actual $34.86.',
    )
    expect(button('Play')).toBeEnabled()
    act(() => vi.advanceTimersByTime(10_000))
    expect(status()).toMatch(/^Day 1 of 5/)
    expect(screen.getByTestId('walk-actual').getAttribute('data-points')).toBe('1')
  })

  it('plays a day at a time, pauses, steps both ways, resets, and stops at the last day', async () => {
    await walkForward()
    vi.useFakeTimers()
    fireEvent.click(button('Play'))
    expect(button('Pause')).not.toHaveAttribute('aria-pressed') // the label says what a press does; no second state
    expect(screen.getByTestId('walk-status')).toHaveAttribute('aria-live', 'off') // no announcement for each day played past
    act(() => vi.advanceTimersByTime(400)) // frameMs(5) = 400
    expect(status()).toMatch(/^Day 2 of 5, 2021-06-22\. Forecast made the evening before: median \$34\.69/)
    act(() => vi.advanceTimersByTime(400))
    expect(status()).toMatch(/^Day 3 of 5/)
    // Day 3: the actuals of three days, the fan of day 3, the fans of days 1 and 2 behind it.
    expect(screen.getByTestId('walk-actual').getAttribute('data-points')).toBe('3')
    expect(screen.getByTestId('walk-fan').getAttribute('data-day')).toBe('2')
    fireEvent.click(button('Pause'))
    expect(screen.getByTestId('walk-status')).toHaveAttribute('aria-live', 'polite') // paused: the day on show is announced
    act(() => vi.advanceTimersByTime(5000))
    expect(status()).toMatch(/^Day 3 of 5/)
    fireEvent.click(button('Step forward'))
    expect(status()).toMatch(/^Day 4 of 5/)
    fireEvent.click(button('Step back'))
    fireEvent.click(button('Step back'))
    expect(status()).toMatch(/^Day 2 of 5/)
    fireEvent.click(button('Reset'))
    expect(status()).toMatch(/^Day 1 of 5/)
    expect(button('Step back')).toBeDisabled()
    fireEvent.click(button('Play'))
    act(() => vi.advanceTimersByTime(10_000))
    expect(status()).toMatch(/^Day 5 of 5/)
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull() // stopped at the end
    expect(screen.getByTestId('walk-status')).toHaveAttribute('aria-live', 'polite') // and the last day is announced
    expect(button('Step forward')).toBeDisabled()
    fireEvent.click(button('Play')) // from the end, it starts again from the first day
    expect(status()).toMatch(/^Day 1 of 5/)
    act(() => vi.advanceTimersByTime(400))
    expect(status()).toMatch(/^Day 2 of 5/)
    expect(screen.getByTestId('walk-status')).toHaveAttribute('aria-live', 'off')
    fireEvent.click(button('Step forward')) // a step while playing stops the walk, and the day is announced
    expect(status()).toMatch(/^Day 3 of 5/)
    expect(screen.getByTestId('walk-status')).toHaveAttribute('aria-live', 'polite')
  })

  it('draws the Student-t interval of the day on show when the t bands are on', async () => {
    await walkForward()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Student-t bands (variance-matched) instead of normal' }))
    // The made-up first test day's t bounds (forecast_aic_walk_forward.data.json): 80% $36.03 to $37.59, 95% $35.45 to $38.21.
    expect(status()).toContain('80% $36.03 to $37.59, 95% $35.45 to $38.21.')
  })

  describe('draws each day where the fan chart above draws it (the same rows, bands and axis)', () => {
    // The walk-forward file with mean_usd moved onto the actual price (so a mark at the mean is told from
    // one at the median) and day 5's 95% band widened to $20 to $60 (so a y range without the bands
    // would differ): the reader re-checks no dollar value (ADR-0001).
    const edited = () =>
      fakeLoad({}, (name, data) => {
        if (name !== 'forecast_aic_walk_forward') return
        data.windows.forEach((w) => w.rows.forEach((r) => (r.mean_usd = r.actual_usd)))
        Object.assign(data.windows[0].rows[4], { lower_95_usd: 20, upper_95_usd: 60 })
      })
    async function page() {
      render(<ForecastPage state={ready()} load={edited()} readReducedMotion={() => false} />)
      fireEvent.click(radio('Method', 'Walk-forward one-step'))
      await screen.findByTestId('walk-chart')
    }
    const walk = () => screen.getByTestId('walk-chart')

    it('the dots: the forecast at its median, the actual at the actual price', async () => {
      await page()
      for (let day = 0; day < 5; day++) {
        const dot = screen.getByTestId('walk-fan').querySelector('circle')!
        near(dot.getAttribute('cy'), pointsOf('median-line')[day][1])
        near(dot.getAttribute('cx'), pointsOf('median-line')[day][0])
        const actual = walk().querySelector('circle.walk-actual-dot')!
        near(actual.getAttribute('cy'), pointsOf('actual-line')[day][1])
        if (day < 4) fireEvent.click(button('Step forward'))
      }
    })

    it('the day’s bars: the 95% one along the 95% band, the 80% one along the 80% band, on the bands’ own scale', async () => {
      await page()
      for (let day = 0; day < 5; day++) {
        for (const [bar, band] of [['line.bar95', 'band-95'], ['line.bar80', 'band-80']] as const) {
          const line = screen.getByTestId('walk-fan').querySelector(bar)!
          const { upper, lower } = edges(band)
          near(line.getAttribute('y1'), lower[lower.length - 1 - day][1]) // the lower edge runs right to left
          near(line.getAttribute('y2'), upper[day][1])
          near(line.getAttribute('x1'), upper[day][0])
        }
        if (day < 4) fireEvent.click(button('Step forward'))
      }
    })

    it('the trail: the earlier days’ 95% and 80% bands and medians, each the fan chart’s own', async () => {
      await page()
      for (let i = 0; i < 3; i++) fireEvent.click(button('Step forward'))
      const days = 3 // the trail holds the days before the one on show
      const trail = screen.getByTestId('walk-trail')
      for (const [cls, band] of [['path.fan-band95', 'band-95'], ['path.fan-band80', 'band-80']] as const) {
        const mine = edges(trail.querySelector(cls)!)
        const full = edges(band)
        expect(mine.upper).toEqual(full.upper.slice(0, days))
        expect(mine.lower).toEqual(full.lower.slice(full.lower.length - days))
      }
      expect(pointsOf(trail.querySelector('path.line')!)).toEqual(pointsOf('median-line').slice(0, days))
    })
  })

  it('reveals the actual line up to the day on show and no further, along the fan chart’s actual line', async () => {
    await walkForward()
    for (let day = 0; day < 5; day++) {
      expect(pointsOf('walk-actual')).toEqual(pointsOf('actual-line').slice(0, day + 1))
      if (day < 4) fireEvent.click(button('Step forward'))
    }
    for (let day = 4; day > 1; day--) fireEvent.click(button('Step back'))
    expect(pointsOf('walk-actual')).toEqual(pointsOf('actual-line').slice(0, 2))
  })

  it('takes every actual price into the y range of both charts, however far it lies from the forecasts', async () => {
    // The first test day's actual price set to $500 against forecasts near $36 (the reader re-checks no dollar
    // value, ADR-0001): every actual point must still lie inside each chart's frame.
    render(<ForecastPage state={ready()} load={fakeLoad({}, (name, data) => name === 'forecast_aic_walk_forward' && (data.windows[0].rows[0].actual_usd = 500))} readReducedMotion={() => false} />)
    fireEvent.click(radio('Method', 'Walk-forward one-step'))
    await screen.findByTestId('walk-chart')
    const inside = (y: number) => y >= 0 && y <= 300 // the charts' viewBox is 720 x 300
    expect(pointsOf('actual-line').map(([, y]) => inside(y))).toEqual([true, true, true, true, true])
    expect(Math.min(...pointsOf('actual-line').map(([, y]) => y))).toBe(pointsOf('actual-line')[0][1]) // $500 is the highest point
    const dot = screen.getByTestId('walk-chart').querySelector('circle.walk-actual-dot')!
    expect(inside(Number(dot.getAttribute('cy')))).toBe(true)
    near(dot.getAttribute('cy'), pointsOf('actual-line')[0][1])
  })

  it('has no timer at all with reduced motion: Play is off, and stepping still works', async () => {
    await walkForward({ reduced: true })
    vi.useFakeTimers()
    expect(button('Play')).toBeDisabled()
    expect(screen.getByText(/asks for reduced motion, so the walk does not play by itself/)).toBeInTheDocument()
    fireEvent.click(button('Play'))
    act(() => vi.advanceTimersByTime(10_000))
    expect(status()).toMatch(/^Day 1 of 5/)
    expect(vi.getTimerCount()).toBe(0)
    fireEvent.click(button('Step forward'))
    fireEvent.click(button('Step forward'))
    expect(status()).toMatch(/^Day 3 of 5/)
  })

  it('stops a walk that is playing when the reader asks for reduced motion', async () => {
    const listeners: (() => void)[] = []
    const mq = { matches: false, addEventListener: (_: string, f: () => void) => listeners.push(f), removeEventListener: () => {} }
    vi.stubGlobal('matchMedia', () => mq)
    await walkForward()
    vi.useFakeTimers()
    fireEvent.click(button('Play'))
    act(() => vi.advanceTimersByTime(400))
    expect(status()).toMatch(/^Day 2 of 5/)
    mq.matches = true
    act(() => listeners.forEach((f) => f()))
    act(() => vi.advanceTimersByTime(5000))
    expect(status()).toMatch(/^Day 2 of 5/)
    expect(button('Play')).toBeDisabled()
    vi.unstubAllGlobals()
  })

  it('stays paused when reduced motion is turned off again, until Play is pressed', async () => {
    // It once resumed on its own: reduced motion stopped the timer but left the walk "playing".
    const listeners: (() => void)[] = []
    const mq = { matches: false, addEventListener: (_: string, f: () => void) => listeners.push(f), removeEventListener: () => {} }
    vi.stubGlobal('matchMedia', () => mq)
    await walkForward()
    vi.useFakeTimers()
    fireEvent.click(button('Play'))
    act(() => vi.advanceTimersByTime(400))
    expect(status()).toMatch(/^Day 2 of 5/)
    mq.matches = true
    act(() => listeners.forEach((f) => f()))
    mq.matches = false
    act(() => listeners.forEach((f) => f()))
    act(() => vi.advanceTimersByTime(5000))
    expect(status()).toMatch(/^Day 2 of 5/)
    expect(vi.getTimerCount()).toBe(0)
    expect(button('Play')).toBeEnabled()
    expect(screen.getByTestId('walk-status')).toHaveAttribute('aria-live', 'polite')
    fireEvent.click(button('Play'))
    act(() => vi.advanceTimersByTime(400))
    expect(status()).toMatch(/^Day 3 of 5/)
    vi.unstubAllGlobals()
  })

  it('starts again, paused on the first day, when the window changes', async () => {
    await walkForward()
    fireEvent.click(button('Step forward'))
    expect(status()).toMatch(/^Day 2 of 5/)
    fireEvent.click(radio('Window', 'Out of sample, 2021-06-28 to 2021-07-23'))
    expect(status()).toMatch(/^Day 1 of 20, 2021-06-28/)
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
  })
})

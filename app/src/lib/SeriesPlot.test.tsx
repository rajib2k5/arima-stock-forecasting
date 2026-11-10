import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PLOT_WIDTH, SeriesPlot } from './SeriesPlot'
import { fakeResizeObserver } from '../test/resize'

const xs = [0, 1, 2, 3]

/**
 * A pointer move at a horizontal screen position. jsdom has no PointerEvent, so testing-library's
 * fireEvent.pointerMove would build a plain Event and drop clientX; a MouseEvent named
 * "pointermove" carries it, and React reads clientX from it.
 */
function pointAt(target: Element, clientX: number) {
  fireEvent(target, new MouseEvent('pointermove', { bubbles: true, clientX }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SeriesPlot', () => {
  it('draws one path per series, broken at nulls, with an accessible name', () => {
    render(<SeriesPlot title="Test plot" xs={xs} series={[{ name: 'a', ys: [1, null, 3, 4], tone: 'primary' }]} yLabel="units" />)
    const svg = screen.getByRole('img', { name: 'Test plot' })
    const paths = svg.querySelectorAll('[data-testid="plot-line"]')
    expect(paths).toHaveLength(1)
    // Two sub-paths: the point before the null, then the two after it.
    expect(paths[0].getAttribute('d')?.match(/M/g)).toHaveLength(2)
    expect(svg).toHaveTextContent('units')
  })

  it('shades each band across the full width of its rows and names it', () => {
    render(
      <SeriesPlot
        title="Bands"
        xs={xs}
        series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]}
        yLabel="u"
        bands={[
          { from: 0, to: 1, kind: 'train', label: 'Train band' },
          { from: 2, to: 3, kind: 'test', label: 'Test band' },
        ]}
      />,
    )
    const bands = screen.getAllByTestId('plot-band')
    expect(bands.map((b) => b.getAttribute('class'))).toEqual(['band band-train', 'band band-test'])
    expect(bands[0]).toHaveTextContent('Train band')
    // The two bands meet with no gap: the first ends exactly where the second begins.
    const end = Number(bands[0].getAttribute('x')) + Number(bands[0].getAttribute('width'))
    expect(end).toBeCloseTo(Number(bands[1].getAttribute('x')), 9)
  })

  it('shows a legend only when there is more than one series', () => {
    const { rerender } = render(<SeriesPlot title="One" xs={xs} series={[{ name: 'only', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" />)
    expect(screen.queryByRole('list')).toBeNull()
    rerender(
      <SeriesPlot
        title="Two"
        xs={xs}
        series={[
          { name: 'KDE', ys: [1, 2, 3, 4], tone: 'primary' },
          { name: 'Normal', ys: [1, 1, 1, 1], tone: 'muted', dashed: true },
        ]}
        yLabel="u"
      />,
    )
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['KDE', 'Normal'])
  })

  it('says so instead of drawing when there is nothing finite to plot', () => {
    render(<SeriesPlot title="Empty" xs={xs} series={[{ name: 'a', ys: [null, null, null, null], tone: 'primary' }]} yLabel="u" />)
    expect(screen.getByText('No data to plot.')).toBeInTheDocument()
  })

  it('moves a cursor with the arrow keys and reads the row out, and Escape clears it', () => {
    render(<SeriesPlot title="Keys" xs={xs} series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" readout={(i) => `row ${i}`} />)
    const svg = screen.getByRole('img', { name: 'Keys' })
    expect(svg).toHaveAttribute('tabindex', '0')
    expect(screen.queryByTestId('plot-cursor')).toBeNull()
    fireEvent.keyDown(svg, { key: 'ArrowLeft' }) // from the last row
    expect(screen.getByTestId('plot-cursor')).toHaveTextContent('row 2')
    fireEvent.keyDown(svg, { key: 'Home' })
    expect(screen.getByTestId('plot-cursor')).toHaveTextContent('row 0')
    fireEvent.keyDown(svg, { key: 'ArrowLeft' }) // clamped at the first row
    expect(screen.getByTestId('plot-cursor')).toHaveTextContent('row 0')
    fireEvent.keyDown(svg, { key: 'ArrowRight', shiftKey: true }) // a big step, clamped at the last row
    expect(screen.getByTestId('plot-cursor')).toHaveTextContent('row 3')
    fireEvent.keyDown(svg, { key: 'Home' })
    fireEvent.keyDown(svg, { key: 'End' })
    expect(screen.getByText('row 3', { selector: 'p' })).toBeInTheDocument() // the live region
    fireEvent.keyDown(svg, { key: 'Escape' })
    expect(screen.queryByTestId('plot-cursor')).toBeNull()
    fireEvent.keyDown(svg, { key: 'a' }) // other keys do nothing
    expect(screen.queryByTestId('plot-cursor')).toBeNull()
  })

  it('puts the cursor on the row nearest the pointer', () => {
    render(<SeriesPlot title="Pointer" xs={xs} series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" readout={(i) => `row ${i}`} />)
    const svg = screen.getByRole('img', { name: 'Pointer' })
    // jsdom has no layout, so give the plot a size: drawn at its natural width, 720 px.
    svg.getBoundingClientRect = () => ({ left: 0, width: PLOT_WIDTH, top: 0, height: 240, right: PLOT_WIDTH, bottom: 240, x: 0, y: 0, toJSON: () => ({}) })
    // The plot area runs from x = 58 to 706, so row 1 sits at 58 + 648 / 3 = 274.
    pointAt(svg, 280)
    expect(screen.getByTestId('plot-cursor')).toHaveTextContent('row 1')
    fireEvent.pointerLeave(svg)
    expect(screen.queryByTestId('plot-cursor')).toBeNull()
  })

  it('draws on a narrower canvas when given a width, and maps the pointer on that canvas', () => {
    render(<SeriesPlot title="Narrow" xs={xs} series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" width={360} readout={(i) => `row ${i}`} />)
    const svg = screen.getByRole('img', { name: 'Narrow' })
    expect(svg).toHaveAttribute('viewBox', '0 0 360 240')
    // Shown at 720 px, twice its drawing width. The plot area runs from 58 to 346 drawing units,
    // so row 2 sits at 58 + 2 * 288 / 3 = 250 units, which is 500 px on screen.
    svg.getBoundingClientRect = () => ({ left: 0, width: 720, top: 0, height: 480, right: 720, bottom: 480, x: 0, y: 0, toJSON: () => ({}) })
    pointAt(svg, 505)
    expect(screen.getByTestId('plot-cursor')).toHaveTextContent('row 2')
  })

  it('ignores a pointer event that carries no position', () => {
    render(<SeriesPlot title="NoPos" xs={xs} series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" readout={(i) => `row ${i}`} />)
    const svg = screen.getByRole('img', { name: 'NoPos' })
    svg.getBoundingClientRect = () => ({ left: 0, width: PLOT_WIDTH, top: 0, height: 240, right: PLOT_WIDTH, bottom: 240, x: 0, y: 0, toJSON: () => ({}) })
    fireEvent.pointerMove(svg) // jsdom: a plain Event, clientX undefined
    expect(screen.queryByTestId('plot-cursor')).toBeNull()
  })

  it('ignores the pointer while the plot has no size (before layout)', () => {
    render(<SeriesPlot title="Unsized" xs={xs} series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" readout={(i) => `row ${i}`} />)
    pointAt(screen.getByRole('img', { name: 'Unsized' }), 280)
    expect(screen.queryByTestId('plot-cursor')).toBeNull()
  })

  it('has no cursor and is not focusable without a readout', () => {
    render(<SeriesPlot title="Static" xs={xs} series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" />)
    const svg = screen.getByRole('img', { name: 'Static' })
    expect(svg).not.toHaveAttribute('tabindex')
    fireEvent.keyDown(svg, { key: 'Home' })
    expect(screen.queryByTestId('plot-cursor')).toBeNull()
  })

  it('draws a zero line only when asked and only when zero is in range', () => {
    const { container, rerender } = render(<SeriesPlot title="Z" xs={xs} series={[{ name: 'a', ys: [-1, 1, -1, 1], tone: 'primary' }]} yLabel="u" zeroLine />)
    expect(container.querySelectorAll('line.zero')).toHaveLength(1)
    rerender(<SeriesPlot title="Z" xs={xs} series={[{ name: 'a', ys: [1, 2, 3, 4], tone: 'primary' }]} yLabel="u" zeroLine />)
    expect(container.querySelectorAll('line.zero')).toHaveLength(0)
  })

  it('draws one unit per pixel in a container narrower than its drawing, so its 10-unit labels stay 10 px on a phone', () => {
    const ro = fakeResizeObserver()
    const years = Array.from({ length: 12 }, (_, k) => ({ x: k, label: String(2015 + k) }))
    const xs12 = years.map((t) => t.x)
    const { container, unmount } = render(<SeriesPlot title="Phone" xs={xs12} series={[{ name: 'a', ys: xs12, tone: 'primary' }]} yLabel="u" xTicks={years} readout={(i) => `row ${i}`} />)
    const svg = screen.getByRole('img', { name: 'Phone' })
    const ticks = () => [...container.querySelectorAll('text.tick')].map((t) => t.textContent)
    expect(svg).toHaveAttribute('viewBox', '0 0 720 240')
    expect(ticks()).toHaveLength(12)
    // A 375 px phone leaves the card 293 px wide: the drawing becomes 293 units, its grid ends at 293 - 14.
    ro.resizeTo(293)
    expect(svg).toHaveAttribute('viewBox', '0 0 293 240')
    expect(container.querySelector('line.grid')).toHaveAttribute('x2', '279')
    // Twelve years 20 units apart would overlap: every second one is drawn.
    expect(ticks()).toEqual(['2015', '2017', '2019', '2021', '2023', '2025'])
    // The pointer maps onto the 293-unit drawing: 100 px is (100 − 58) / 221 × 11 = 2.1 rows along a plot area from 58 to 279.
    svg.getBoundingClientRect = () => ({ left: 0, width: 293, top: 0, height: 240, right: 293, bottom: 240, x: 0, y: 0, toJSON: () => ({}) })
    pointAt(svg, 100)
    expect(screen.getByTestId('plot-cursor')).toHaveTextContent('row 2')
    // A desktop card wider than the drawing keeps the drawing as it was.
    ro.resizeTo(1018)
    expect(svg).toHaveAttribute('viewBox', '0 0 720 240')
    expect(ticks()).toHaveLength(12)
    expect(ro.observed()).toBe(1)
    unmount()
    expect(ro.observed()).toBe(0)
  })

  it('labels the x axis with nice ticks when no ticks are given', () => {
    const { container } = render(<SeriesPlot title="X" xs={[0, 0.1, 0.2]} series={[{ name: 'a', ys: [1, 2, 3], tone: 'primary' }]} yLabel="u" />)
    const labels = [...container.querySelectorAll('text.tick')].map((t) => t.textContent)
    expect(labels).toEqual(['0.00', '0.05', '0.10', '0.15', '0.20'])
  })
})

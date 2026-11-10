import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CorrelogramPlot } from './CorrelogramPlot'
import type { CorrelogramBar } from './correlogram'
import { fakeResizeObserver } from '../test/resize'

const BARS: CorrelogramBar[] = [
  { lag: 1, value: -0.08, band: 0.0434, outside: true },
  { lag: 2, value: 0.01, band: 0.0436, outside: false },
  { lag: 3, value: -0.02, band: 0.0437, outside: false },
]

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CorrelogramPlot', () => {
  it('draws one bar per lag, the band, and marks the bars past it', () => {
    render(<CorrelogramPlot title="ACF of the first difference" label="ACF" bars={BARS} />)
    expect(screen.getByRole('img', { name: 'ACF of the first difference' })).toBeInTheDocument()
    const bars = screen.getAllByTestId('correlogram-bar')
    expect(bars).toHaveLength(3)
    expect(bars.map((b) => b.getAttribute('class'))).toEqual(['bar outside', 'bar', 'bar'])
    expect(screen.getByTestId('correlogram-band').getAttribute('d')).toMatch(/^M.* Z$/)
  })

  it('draws a negative bar below the zero line and a positive one above it', () => {
    render(<CorrelogramPlot title="t" label="ACF" bars={BARS} />)
    const [down, up] = screen.getAllByTestId('correlogram-bar')
    expect(Number(down.getAttribute('y2'))).toBeGreaterThan(Number(down.getAttribute('y1')))
    expect(Number(up.getAttribute('y2'))).toBeLessThan(Number(up.getAttribute('y1')))
  })

  it('reads lags out from the keyboard and clears on Escape', () => {
    render(<CorrelogramPlot title="t" label="PACF" bars={BARS} />)
    const svg = screen.getByRole('img')
    fireEvent.keyDown(svg, { key: 'ArrowRight' })
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 1 · PACF −0.0800 · band ±0.0434 · beyond the band')
    fireEvent.keyDown(svg, { key: 'ArrowRight' })
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 2 · PACF 0.0100')
    fireEvent.keyDown(svg, { key: 'End' })
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 3')
    fireEvent.keyDown(svg, { key: 'ArrowRight' })
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 3') // stays on the last lag
    fireEvent.keyDown(svg, { key: 'Home' })
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 1')
    fireEvent.keyDown(svg, { key: 'ArrowLeft' })
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 1')
    fireEvent.keyDown(svg, { key: 'Escape' })
    expect(screen.queryByTestId('correlogram-cursor')).toBeNull()
  })

  it('moves the cursor to the lag under the pointer', () => {
    render(<CorrelogramPlot title="t" label="ACF" bars={BARS} width={420} />)
    const svg = screen.getByRole('img')
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 420, height: 220, right: 420, bottom: 220, x: 0, y: 0, toJSON: () => ({}) })
    // jsdom has no PointerEvent: a MouseEvent named pointermove carries clientX (see the M1 walkthrough).
    fireEvent(svg, new MouseEvent('pointermove', { bubbles: true, clientX: 405 }))
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 3')
    fireEvent(svg, new MouseEvent('pointermove', { bubbles: true, clientX: 50 }))
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 1')
    fireEvent.pointerLeave(svg)
    expect(screen.queryByTestId('correlogram-cursor')).toBeNull()
  })

  it('draws one unit per pixel in a phone-width card, keeping its lag labels, and maps the pointer on that drawing', () => {
    const ro = fakeResizeObserver()
    const fifty = Array.from({ length: 50 }, (_, k) => ({ lag: k + 1, value: 0.01, band: 0.04, outside: false }))
    const { container } = render(<CorrelogramPlot title="fifty" label="ACF" bars={fifty} />)
    render(<CorrelogramPlot title="three" label="ACF" bars={BARS} />)
    const svg = screen.getByRole('img', { name: 'three' })
    expect(svg).toHaveAttribute('viewBox', '0 0 420 220')
    ro.resizeTo(293)
    expect(svg).toHaveAttribute('viewBox', '0 0 293 220')
    expect(svg.querySelector('line.zero')).toHaveAttribute('x2', '283')
    // Fifty lags on 237 units still leave room for every label.
    expect([...container.querySelectorAll('text.tick')].map((t) => t.textContent)).toEqual(['1', '10', '20', '30', '40', '50'])
    // 120 px is 0.5 + (120 − 46) / 237 × 3 = lag 1.4 along a plot area from 46 to 283.
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 293, height: 220, right: 293, bottom: 220, x: 0, y: 0, toJSON: () => ({}) })
    fireEvent(svg, new MouseEvent('pointermove', { bubbles: true, clientX: 120 }))
    expect(screen.getByTestId('correlogram-cursor')).toHaveTextContent('lag 1')
  })

  it('says so when there is nothing to draw', () => {
    render(<CorrelogramPlot title="t" label="ACF" bars={[]} />)
    expect(screen.getByText('No lags to plot.')).toBeInTheDocument()
  })
})

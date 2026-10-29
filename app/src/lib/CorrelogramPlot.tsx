/**
 * A dependency-free SVG correlogram: one bar per lag, the 95% band shaded around zero, and a
 * hover / keyboard cursor that reads out one lag. It draws what plot_acf and plot_pacf draw, from
 * the values acf_pacf.json exports. Colours come from CSS custom properties (index.css), so the
 * chart follows the light and dark themes.
 */
import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { bandPath, correlogramDomain, lagTicks, readoutText, type CorrelogramBar } from './correlogram'
import { formatTick, linearScale, nearestIndex, niceStep, niceTicks } from './plot'

export interface CorrelogramPlotProps {
  title: string
  /** "ACF" or "PACF", for the readout. */
  label: string
  bars: readonly CorrelogramBar[]
  width?: number
  height?: number
}

const PAD = { l: 46, r: 10, t: 22, b: 24 }

export function CorrelogramPlot({ title, label, bars, width = 420, height = 220 }: CorrelogramPlotProps) {
  const [cursor, setCursor] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const layout = useMemo(() => {
    if (bars.length === 0) return null
    const lags = bars.map((b) => b.lag)
    const xDomain: [number, number] = [lags[0] - 0.5, lags[lags.length - 1] + 0.5]
    const yDomain = correlogramDomain(bars)
    const sx = linearScale(xDomain, [PAD.l, width - PAD.r])
    const sy = linearScale(yDomain, [height - PAD.b, PAD.t])
    const toX = linearScale([PAD.l, width - PAD.r], xDomain)
    const half = (sx(1) - sx(0)) / 2
    const yTicks = niceTicks(yDomain[0], yDomain[1], 4)
    const yStep = niceStep(yDomain[1] - yDomain[0], 4)
    return { lags, sx, sy, toX, half, yTicks, yStep, band: bandPath(bars, sx, sy, half) }
  }, [bars, width, height])
  if (!layout) return <p className="sub">No lags to plot.</p>
  const { lags, sx, sy, toX, half, yTicks, yStep, band } = layout

  const moveTo = (i: number) => setCursor(Math.max(0, Math.min(bars.length - 1, i)))
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return
    const px = ((e.clientX - rect.left) / rect.width) * width
    if (!Number.isFinite(px)) return
    moveTo(nearestIndex(lags, toX(px)))
  }
  const onKeyDown = (e: KeyboardEvent<SVGSVGElement>) => {
    const at = cursor ?? 0
    if (e.key === 'ArrowLeft') moveTo(at - 1)
    else if (e.key === 'ArrowRight') moveTo(cursor === null ? 0 : at + 1)
    else if (e.key === 'Home') moveTo(0)
    else if (e.key === 'End') moveTo(bars.length - 1)
    else if (e.key === 'Escape') setCursor(null)
    else return
    e.preventDefault()
  }
  const barWidth = Math.max(1, Math.min(6, half * 0.9))
  return (
    <figure className="plot correlogram">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={title}
        tabIndex={0}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setCursor(null)}
        onKeyDown={onKeyDown}
      >
        <path className="band-area" d={band} data-testid="correlogram-band" />
        {yTicks.map((t) => (
          <g key={t} className="tick">
            <line className="grid" x1={PAD.l} x2={width - PAD.r} y1={sy(t)} y2={sy(t)} />
            <text x={PAD.l - 6} y={sy(t) + 3.5} textAnchor="end">
              {formatTick(t, yStep)}
            </text>
          </g>
        ))}
        <line className="zero" x1={PAD.l} x2={width - PAD.r} y1={sy(0)} y2={sy(0)} />
        {lagTicks(bars).map((lag) => (
          <text key={lag} className="tick" x={sx(lag)} y={height - 8} textAnchor="middle">
            {lag}
          </text>
        ))}
        <text className="axis-label" x={4} y={13}>
          {label}
        </text>
        {bars.map((b) => (
          <line
            key={b.lag}
            className={b.outside ? 'bar outside' : 'bar'}
            data-testid="correlogram-bar"
            x1={sx(b.lag)}
            x2={sx(b.lag)}
            y1={sy(0)}
            y2={sy(b.value)}
            strokeWidth={barWidth}
          />
        ))}
        {cursor !== null && (
          <g className="cursor" data-testid="correlogram-cursor">
            <line x1={sx(bars[cursor].lag)} x2={sx(bars[cursor].lag)} y1={PAD.t} y2={height - PAD.b} />
            <text x={width - PAD.r} y={13} textAnchor="end">
              {readoutText(label, bars[cursor])}
            </text>
          </g>
        )}
      </svg>
      <p className="visually-hidden" aria-live="polite">
        {cursor !== null ? readoutText(label, bars[cursor]) : ''}
      </p>
    </figure>
  )
}

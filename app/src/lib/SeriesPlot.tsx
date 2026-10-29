/**
 * A dependency-free SVG plot of one or more series against a shared x, with optional shaded bands,
 * gaps where a value is null, and a hover / keyboard cursor that reads out one row.
 *
 * Colours come from CSS custom properties (see `.plot` in index.css), so the plot follows the light
 * and dark themes without re-rendering. All geometry is done by the pure helpers in plot.ts.
 */
import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { extent, formatTick, gapPath, linearScale, nearestIndex, niceStep, niceTicks } from './plot'

export type PlotTone = 'primary' | 'secondary' | 'muted'

export interface PlotSeries {
  name: string
  ys: readonly (number | null)[]
  tone: PlotTone
  dashed?: boolean
}

export interface PlotBand {
  /** First and last x covered, both inclusive. */
  from: number
  to: number
  /** CSS suffix: the band is drawn with class `band band-<kind>`. */
  kind: string
  label: string
}

export interface PlotTick {
  x: number
  label: string
}

export interface SeriesPlotProps {
  title: string
  xs: readonly number[]
  series: readonly PlotSeries[]
  yLabel: string
  bands?: readonly PlotBand[]
  xTicks?: readonly PlotTick[]
  height?: number
  /**
   * Width of the drawing in SVG units. The SVG scales to its container, so text shrinks with it:
   * a small panel uses a narrower drawing to keep its 10-unit labels readable.
   */
  width?: number
  /** Draw a horizontal line at y = 0 when 0 is inside the y range. */
  zeroLine?: boolean
  /** Text for the cursor readout at row i; without it the plot has no cursor. */
  readout?: (i: number) => string
}

export const PLOT_WIDTH = 720
const PAD = { l: 58, r: 14, t: 26, b: 26 }

export function SeriesPlot({ title, xs, series, yLabel, bands = [], xTicks, height = 240, width = PLOT_WIDTH, zeroLine = false, readout }: SeriesPlotProps) {
  const [cursor, setCursor] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const layout = useMemo(() => {
    const yExt = extent(series.map((s) => s.ys))
    const xExt = extent([xs])
    if (!yExt || !xExt) return null
    // A little head-room above and below, so the line never touches the frame.
    const pad = (yExt[1] - yExt[0]) * 0.04 || Math.abs(yExt[0]) * 0.04 || 1
    const yDomain: [number, number] = [yExt[0] - pad, yExt[1] + pad]
    const sx = linearScale(xExt, [PAD.l, width - PAD.r])
    const sy = linearScale(yDomain, [height - PAD.b, PAD.t])
    const toX = linearScale([PAD.l, width - PAD.r], xExt)
    const yTicks = niceTicks(yDomain[0], yDomain[1], 4)
    const yStep = niceStep(yDomain[1] - yDomain[0], 4)
    const xt = xTicks ?? niceTicks(xExt[0], xExt[1], 5).map((x) => ({ x, label: formatTick(x, niceStep(xExt[1] - xExt[0], 5)) }))
    // Half the spacing between neighbouring x values, so a band covers its rows' full width.
    const half = xs.length > 1 ? (sx(xs[xs.length - 1]) - sx(xs[0])) / (xs.length - 1) / 2 : 0
    const paths = series.map((s) => gapPath(xs, s.ys, sx, sy))
    return { sx, sy, toX, yTicks, yStep, xt, half, paths, yDomain }
  }, [xs, series, xTicks, height, width])

  if (!layout) return <p className="sub">No data to plot.</p>
  const { sx, sy, toX, yTicks, yStep, xt, half, paths, yDomain } = layout

  const moveTo = (i: number) => setCursor(Math.max(0, Math.min(xs.length - 1, i)))
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return
    const px = ((e.clientX - rect.left) / rect.width) * width
    // An event without a position would give NaN, and nearestIndex(NaN) would pick a row at random.
    if (!Number.isFinite(px)) return
    moveTo(nearestIndex(xs, toX(px)))
  }
  const onKeyDown = (e: KeyboardEvent<SVGSVGElement>) => {
    const step = e.shiftKey ? 20 : 1
    const at = cursor ?? xs.length - 1
    if (e.key === 'ArrowLeft') moveTo(at - step)
    else if (e.key === 'ArrowRight') moveTo(at + step)
    else if (e.key === 'Home') moveTo(0)
    else if (e.key === 'End') moveTo(xs.length - 1)
    else if (e.key === 'Escape') setCursor(null)
    else return
    e.preventDefault()
  }

  const interactive = readout !== undefined
  return (
    <figure className="plot">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={title}
        tabIndex={interactive ? 0 : undefined}
        onPointerMove={interactive ? onPointerMove : undefined}
        onPointerLeave={interactive ? () => setCursor(null) : undefined}
        onKeyDown={interactive ? onKeyDown : undefined}
      >
        {bands.map((b) => (
          <rect
            key={`${b.kind}-${b.from}`}
            className={`band band-${b.kind}`}
            data-testid="plot-band"
            x={sx(b.from) - half}
            y={PAD.t}
            width={Math.max(sx(b.to) - sx(b.from) + 2 * half, 1)}
            height={height - PAD.t - PAD.b}
          >
            <title>{b.label}</title>
          </rect>
        ))}
        {yTicks.map((t) => (
          <g key={t} className="tick">
            <line className="grid" x1={PAD.l} x2={width - PAD.r} y1={sy(t)} y2={sy(t)} />
            <text x={PAD.l - 6} y={sy(t) + 3.5} textAnchor="end">
              {formatTick(t, yStep)}
            </text>
          </g>
        ))}
        {zeroLine && yDomain[0] < 0 && yDomain[1] > 0 && <line className="zero" x1={PAD.l} x2={width - PAD.r} y1={sy(0)} y2={sy(0)} />}
        {xt.map((t) => (
          <text key={`${t.x}-${t.label}`} className="tick" x={sx(t.x)} y={height - 8} textAnchor="middle">
            {t.label}
          </text>
        ))}
        <text className="axis-label" x={4} y={13}>
          {yLabel}
        </text>
        {series.map((s, k) => (
          <path key={s.name} className={`line line-${s.tone}${s.dashed ? ' dashed' : ''}`} d={paths[k]} data-testid="plot-line" />
        ))}
        {interactive && cursor !== null && (
          <g className="cursor" data-testid="plot-cursor">
            <line x1={sx(xs[cursor])} x2={sx(xs[cursor])} y1={PAD.t} y2={height - PAD.b} />
            <text x={width - PAD.r} y={13} textAnchor="end">
              {readout(cursor)}
            </text>
          </g>
        )}
      </svg>
      {interactive && (
        <p className="visually-hidden" aria-live="polite">
          {cursor !== null ? readout(cursor) : ''}
        </p>
      )}
      {series.length > 1 && (
        <figcaption>
          <ul className="plot-legend">
            {series.map((s) => (
              <li key={s.name}>
                <span className={`swatch line-${s.tone}${s.dashed ? ' dashed' : ''}`} aria-hidden="true" />
                {s.name}
              </li>
            ))}
          </ul>
        </figcaption>
      )}
    </figure>
  )
}

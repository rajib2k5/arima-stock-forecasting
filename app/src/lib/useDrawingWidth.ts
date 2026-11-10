/**
 * The drawing width of a plot, kept in step with its container by a ResizeObserver (plot.drawingWidth
 * decides the number). Browser-bound, unlike the pure helpers beside it, because the plot components
 * that use it live in src/lib. Without ResizeObserver (jsdom), or before the container is measured,
 * the width is the nominal one: the drawing as it was before phones were considered.
 */
import { useLayoutEffect, useState } from 'react'
import { drawingWidth } from './plot'

/** Returns a ref callback for the plot's container and the width to draw at. */
export function useDrawingWidth(nominal: number): [(el: Element | null) => void, number] {
  const [el, setEl] = useState<Element | null>(null)
  const [px, setPx] = useState<number | null>(null)
  useLayoutEffect(() => {
    if (!el || typeof ResizeObserver === 'undefined') return
    // Measured once before the first paint, then on every change of the container's width.
    setPx(Math.round(el.getBoundingClientRect().width))
    const ro = new ResizeObserver((entries) => {
      const entry = entries[entries.length - 1]
      if (entry) setPx(Math.round(entry.contentRect.width))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [el])
  return [setEl, drawingWidth(px, nominal)]
}

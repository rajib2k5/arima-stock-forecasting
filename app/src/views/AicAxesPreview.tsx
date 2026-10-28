/**
 * 3D wiring proof: empty (p, q, AIC) axes. The heavy scene is loaded lazily and only when the
 * browser can make a WebGL2 context; otherwise (or if the scene throws) a static description
 * of the same axes is shown, so the page never breaks for want of a GPU.
 */
import { Component, lazy, Suspense, useMemo, type ComponentType, type ErrorInfo, type ReactNode } from 'react'
import { describeAxes, motionSettings } from '../lib/aicAxes'
import { hasWebGL, prefersReducedMotion } from '../lib/capabilities'
import { useReducedMotion } from './hooks'
import type { SceneProps } from './AicAxesScene'

const LazyScene = lazy(() => import('./AicAxesScene'))

export const PREVIEW_CAPTION = 'AIC landscape arrives in milestone 2 — no data is drawn yet'

export function AicAxesFallback() {
  return (
    <div className="aic-fallback">
      <p>
        <strong>3D preview unavailable.</strong> This browser cannot create a WebGL2 context (or the scene failed to start), so the
        interactive axes are not drawn. They would show:
      </p>
      <ul>
        {describeAxes().map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
  )
}

/** Falls back to the static description if the 3D scene throws while loading or rendering. */
class PreviewBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn('3D preview failed, showing the static fallback:', error.message, info.componentStack)
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export function AicAxesPreview({
  webglAvailable = hasWebGL,
  readReducedMotion = prefersReducedMotion,
  Scene = LazyScene,
}: {
  webglAvailable?: () => boolean
  readReducedMotion?: () => boolean
  Scene?: ComponentType<SceneProps>
}) {
  const supported = useMemo(() => webglAvailable(), [webglAvailable])
  const reduced = useReducedMotion(readReducedMotion)
  return (
    <figure className="aic-preview">
      {supported ? (
        <PreviewBoundary fallback={<AicAxesFallback />}>
          <Suspense fallback={<p className="sub" role="status">Loading 3D preview…</p>}>
            <Scene motion={motionSettings(reduced)} />
          </Suspense>
        </PreviewBoundary>
      ) : (
        <AicAxesFallback />
      )}
      <figcaption>{PREVIEW_CAPTION}</figcaption>
    </figure>
  )
}

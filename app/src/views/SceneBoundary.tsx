/**
 * Shows `fallback` instead of a 3D scene that throws while it loads or renders (no WebGL, a lost
 * context, a shader error), so a page never breaks for want of a GPU. Used by the Architecture
 * page's axes preview and by the AIC landscape.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'

/** Falls back to the static description if the 3D scene throws while loading or rendering. */
export class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn('3D scene failed, showing the static fallback:', error.message, info.componentStack)
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

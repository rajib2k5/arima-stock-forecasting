import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, renderHook, screen } from '@testing-library/react'
import { lazy } from 'react'
import { AicAxesPreview, PREVIEW_CAPTION } from './AicAxesPreview'
import { useThemeColors } from './hooks'
import type { SceneProps } from './AicAxesScene'

const CAPTION = 'Empty axes: the AIC landscape page draws the fitted grid on them'

function FakeScene({ motion }: SceneProps) {
  return <div data-testid="scene" data-autorotate={String(motion.autoRotate)} data-frameloop={motion.frameloop} />
}
function ThrowingScene(): never {
  throw new Error('Error creating WebGL context.')
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('AicAxesPreview without WebGL (jsdom)', () => {
  it('renders the static fallback and the caption, and never mounts a scene', () => {
    render(<AicAxesPreview />)
    expect(screen.getByText('3D preview unavailable.')).toBeInTheDocument()
    expect(screen.getByText('p: 0 to 5')).toBeInTheDocument()
    expect(screen.getByText('q: 0 to 5')).toBeInTheDocument()
    expect(screen.getByText('AIC: lower is better')).toBeInTheDocument()
    expect(screen.getByText(CAPTION)).toBeInTheDocument()
    expect(document.querySelector('.aic-canvas')).toBeNull()
    expect(document.querySelector('canvas')).toBeNull()
  })
  it('exports the caption the page promises', () => {
    expect(PREVIEW_CAPTION).toBe(CAPTION)
  })
  it('does not even try to build the scene when WebGL is unavailable', () => {
    const Spy = vi.fn(FakeScene)
    render(<AicAxesPreview webglAvailable={() => false} Scene={Spy} />)
    expect(Spy).not.toHaveBeenCalled()
    expect(screen.getByText('3D preview unavailable.')).toBeInTheDocument()
  })
})

describe('AicAxesPreview with WebGL', () => {
  it('mounts the scene with auto-rotate on and a continuous loop when motion is allowed', () => {
    render(<AicAxesPreview webglAvailable={() => true} readReducedMotion={() => false} Scene={FakeScene} />)
    expect(screen.getByTestId('scene')).toHaveAttribute('data-autorotate', 'true')
    expect(screen.getByTestId('scene')).toHaveAttribute('data-frameloop', 'always')
    expect(screen.queryByText('3D preview unavailable.')).toBeNull()
    expect(screen.getByText(CAPTION)).toBeInTheDocument()
  })
  it('turns auto-rotate off and renders on demand when the reader prefers reduced motion', () => {
    render(<AicAxesPreview webglAvailable={() => true} readReducedMotion={() => true} Scene={FakeScene} />)
    expect(screen.getByTestId('scene')).toHaveAttribute('data-autorotate', 'false')
    expect(screen.getByTestId('scene')).toHaveAttribute('data-frameloop', 'demand')
  })
  it('follows a live change of the reduced-motion preference', () => {
    let listener: (() => void) | undefined
    const mq = {
      matches: false,
      addEventListener: (_t: string, l: () => void) => (listener = l),
      removeEventListener: () => (listener = undefined),
    }
    vi.stubGlobal('matchMedia', () => mq)
    render(<AicAxesPreview webglAvailable={() => true} readReducedMotion={() => mq.matches} Scene={FakeScene} />)
    expect(screen.getByTestId('scene')).toHaveAttribute('data-autorotate', 'true')
    mq.matches = true
    act(() => listener?.())
    expect(screen.getByTestId('scene')).toHaveAttribute('data-autorotate', 'false')
  })
  it('shows a loading status while the lazy scene chunk is still arriving', () => {
    const Pending = lazy(() => new Promise<{ default: typeof FakeScene }>(() => {}))
    render(<AicAxesPreview webglAvailable={() => true} Scene={Pending} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading 3D preview…')
    expect(screen.getByText(CAPTION)).toBeInTheDocument()
  })
  it('falls back to the static description if the scene throws (probe said yes, context creation failed)', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(<AicAxesPreview webglAvailable={() => true} Scene={ThrowingScene} />)
    expect(screen.getByText('3D preview unavailable.')).toBeInTheDocument()
    expect(screen.getByText('AIC: lower is better')).toBeInTheDocument()
    expect(screen.getByText(CAPTION)).toBeInTheDocument()
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0][1])).toContain('Error creating WebGL context.')
  })
})

describe('useThemeColors', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('style')
    document.documentElement.removeAttribute('data-theme')
  })
  it('reads the CSS colour tokens and refreshes them when data-theme flips', async () => {
    const root = document.documentElement
    root.style.setProperty('--ink', '#111111')
    root.style.setProperty('--accent', '#222222')
    root.setAttribute('data-theme', 'dark')
    const { result } = renderHook(() => useThemeColors())
    expect(result.current.ink).toBe('#111111')
    expect(result.current.accent).toBe('#222222')
    // tokens not defined on the page fall back to the dark palette
    expect(result.current.line).toBe('#2c3547')

    root.style.setProperty('--ink', '#eeeeee')
    await act(async () => {
      root.setAttribute('data-theme', 'light')
      await Promise.resolve()
    })
    expect(result.current.ink).toBe('#eeeeee')
  })
})

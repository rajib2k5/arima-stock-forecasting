import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ArchDiagram, SequenceDiagram, ActivityDiagram } from './diagrams'

afterEach(() => {
  vi.useRealTimers()
})

describe('ArchDiagram', () => {
  it('renders every layer label and box, with flowing connector arrows between layers', () => {
    const { container } = render(
      <ArchDiagram
        layers={[
          { label: 'Data', boxes: ['raw.csv', 'cache'] },
          { label: 'Core', boxes: ['engine'] },
          { label: 'UI', boxes: ['Table', 'Chart', 'Notes'] },
        ]}
      />,
    )
    for (const t of ['DATA', 'CORE', 'UI', 'raw.csv', 'engine', 'Notes']) expect(screen.getByText(t)).toBeInTheDocument()
    expect(container.querySelectorAll('rect')).toHaveLength(6)
    // continuous dashed-flow animation class on both inter-layer connectors
    expect(container.querySelectorAll('line.qd-arch-flow')).toHaveLength(2)
  })
})

describe('SequenceDiagram (looping stepper)', () => {
  const actors = ['User', 'Engine', 'Store']
  const steps = [
    { from: 0, to: 1, label: 'run()' },
    { from: 1, to: 1, label: 'validate params' },
    { from: 1, to: 2, label: 'read as-of' },
    { from: 2, to: 1, label: 'rows' },
  ]
  it('starts with step 0 running, others pending, and a traveling dot on the active arrow', () => {
    vi.useFakeTimers()
    const { container } = render(<SequenceDiagram actors={actors} steps={steps} />)
    expect(container.querySelectorAll('.qd-seq-line.run')).toHaveLength(1)
    expect(container.querySelectorAll('.qd-seq-line.pending')).toHaveLength(2) // self-step is a note
    expect(screen.getByTestId('qd-seq-dot')).toBeInTheDocument()
    expect(screen.getByText('↺ validate params')).toBeInTheDocument()
  })
  it('advances on the timer, completes all arrows, then loops back to the start', () => {
    vi.useFakeTimers()
    const { container } = render(<SequenceDiagram actors={actors} steps={steps} />)
    act(() => {
      vi.advanceTimersByTime(850 * 3) // phases 1,2,3 -> last arrow running
    })
    expect(container.querySelectorAll('.qd-seq-line.done')).toHaveLength(2)
    expect(container.querySelectorAll('.qd-seq-line.run')).toHaveLength(1)
    act(() => {
      vi.advanceTimersByTime(850) // phase 4: hold — everything drawn
    })
    expect(container.querySelectorAll('.qd-seq-line.done')).toHaveLength(3)
    expect(container.querySelector('.qd-seq-line.run')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(850 * 3) // remaining holds -> wraps to phase 0
    })
    expect(container.querySelectorAll('.qd-seq-line.pending')).toHaveLength(2)
    expect(container.querySelectorAll('.qd-seq-line.run')).toHaveLength(1)
  })
  it('replay resets to the first step and fires the callback', () => {
    vi.useFakeTimers()
    const onReplay = vi.fn()
    const { container } = render(<SequenceDiagram actors={actors} steps={steps} onReplay={onReplay} />)
    act(() => {
      vi.advanceTimersByTime(850 * 4)
    })
    expect(container.querySelector('.qd-seq-line.run')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Replay sequence' }))
    expect(onReplay).toHaveBeenCalledTimes(1)
    expect(container.querySelectorAll('.qd-seq-line.run')).toHaveLength(1)
    expect(container.querySelectorAll('.qd-seq-line.done')).toHaveLength(0)
  })
})

describe('ActivityDiagram (walking token)', () => {
  const nodes = [
    { id: 's', label: 'load', type: 'start' as const },
    { id: 'k', label: 'Cache hit?', type: 'decision' as const },
    { id: 'live', label: 'fetch remote' },
    { id: 'syn', label: 'read cache' },
    { id: 'e', label: 'render', type: 'end' as const },
  ]
  const edges = [
    { from: 's', to: 'k' },
    { from: 'k', to: 'live', label: 'yes' },
    { from: 'k', to: 'syn', label: 'no' },
    { from: 'live', to: 'syn' },
    { from: 'syn', to: 'e' },
  ]
  it('renders shapes, decision diamond, side-routed edges, and ignores unknown edge ids', () => {
    vi.useFakeTimers()
    const { container } = render(<ActivityDiagram nodes={nodes} edges={[...edges, { from: 'ghost', to: 'e' }]} />)
    expect(screen.getByText('Cache hit?')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-testid="qd-act-decision"]')).toHaveLength(1)
    expect(container.querySelectorAll('[data-testid="qd-act-side"]').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('yes')).toBeInTheDocument()
  })
  it('walks the token down the flow and loops', () => {
    vi.useFakeTimers()
    render(<ActivityDiagram nodes={nodes} edges={edges} />)
    const at = () => screen.getByTestId('qd-act-token').style.transform
    expect(at()).toBe('translateY(0px)')
    act(() => {
      vi.advanceTimersByTime(800)
    })
    expect(at()).toBe('translateY(74px)')
    act(() => {
      vi.advanceTimersByTime(800 * 3) // reach last node
    })
    expect(at()).toBe(`translateY(${74 * 4}px)`)
    act(() => {
      vi.advanceTimersByTime(800) // hold phase: token hidden
    })
    expect(screen.queryByTestId('qd-act-token')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(800) // loops back to node 0
    })
    expect(at()).toBe('translateY(0px)')
  })
})

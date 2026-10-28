import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { AppShell } from './shell'
import { resetMemoryFallback, safeStorage } from './storage'

const PAGES = [
  { id: 'about', label: 'About', render: () => <p>about-content</p> },
  { id: 'analysis', label: 'Analysis', render: () => <p>analysis-content</p> },
]

const STORE = safeStorage()

function shell(storage = STORE) {
  return <AppShell slug="test-app" title="Test App" subtitle="A test" pages={PAGES} storage={storage} />
}

beforeEach(() => {
  resetMemoryFallback()
  STORE.removeItem('arima:test-app:theme')
  window.location.hash = ''
  document.documentElement.removeAttribute('data-theme')
})

describe('AppShell navigation', () => {
  it('renders the nav with exactly the app pages, first page active', () => {
    render(shell())
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Analysis'])
    expect(screen.getByText('about-content')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'About' })).toHaveAttribute('aria-current', 'page')
  })
  it('has no Admin or Metrics page: settings, keys and usage counters do not exist in this app', () => {
    render(shell())
    expect(screen.queryByRole('link', { name: 'Admin' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Metrics' })).toBeNull()
  })
  it('treats a #/metrics hash as an unknown route and shows the first page', () => {
    window.location.hash = '#/metrics'
    render(shell())
    expect(screen.getByText('about-content')).toBeInTheDocument()
    expect(screen.queryByText('Metrics — this app, this browser')).toBeNull()
  })
  it('switches pages on nav click and updates the hash', () => {
    render(shell())
    fireEvent.click(screen.getByRole('link', { name: 'Analysis' }))
    expect(screen.getByText('analysis-content')).toBeInTheDocument()
    expect(screen.queryByText('about-content')).not.toBeInTheDocument()
    expect(window.location.hash).toBe('#/analysis')
  })
  it('opens the page named by the URL hash on mount', () => {
    window.location.hash = '#/analysis'
    render(shell())
    expect(screen.getByText('analysis-content')).toBeInTheDocument()
  })
  it('falls back to the first page for an unknown hash', () => {
    window.location.hash = '#/nope'
    render(shell())
    expect(screen.getByText('about-content')).toBeInTheDocument()
  })
})

describe('Theme toggle', () => {
  it('renders top-right, toggles light/dark on the document element, and persists', () => {
    render(shell())
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    const btn = screen.getByRole('button', { name: 'Switch to light theme' })
    fireEvent.click(btn)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(STORE.getItem('arima:test-app:theme')).toBe('light')
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(STORE.getItem('arima:test-app:theme')).toBe('dark')
  })
  it('honors a stored theme preference on mount', () => {
    STORE.setItem('arima:test-app:theme', 'light')
    render(shell())
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
  })
})

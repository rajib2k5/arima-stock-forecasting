import { lazy, Suspense } from 'react'
import { AppShell } from './lib/shell'
import { useMeta } from './data/useMeta'
import { EXPLORER_ARTIFACTS, FIT_ARTIFACTS, FORECAST_ARTIFACTS, hasArtifacts, LANDSCAPE_ARTIFACTS, STATIONARITY_ARTIFACTS } from './lib/gate'
import { AboutView } from './views/AboutView'
import { ArchitectureView } from './views/ArchitectureView'

const APP_SLUG = 'arima-stock-forecasting'

// Dynamic imports: each data page's code lands in its own chunk, fetched only when the page opens.
const PriceExplorerView = lazy(() => import('./views/PriceExplorerView'))
const StationarityView = lazy(() => import('./views/StationarityView'))
const AicLandscapeView = lazy(() => import('./views/AicLandscapeView'))
const FitView = lazy(() => import('./views/FitView'))
const ForecastView = lazy(() => import('./views/ForecastView'))

function loading(what: string) {
  return (
    <p className="sub" role="status">
      Loading the {what}…
    </p>
  )
}

export default function App() {
  const meta = useMeta()
  // meta.json is the gate: the explorer is offered only once meta lists both files it draws.
  const explorer = meta.status === 'ready' && hasArtifacts(meta.meta, EXPLORER_ARTIFACTS)
  const stationarity = meta.status === 'ready' && hasArtifacts(meta.meta, STATIONARITY_ARTIFACTS)
  const landscape = meta.status === 'ready' && hasArtifacts(meta.meta, LANDSCAPE_ARTIFACTS)
  const fit = meta.status === 'ready' && hasArtifacts(meta.meta, FIT_ARTIFACTS)
  const forecast = meta.status === 'ready' && hasArtifacts(meta.meta, FORECAST_ARTIFACTS)
  return (
    <AppShell
      slug={APP_SLUG}
      title="ARIMA stock forecasting, done carefully"
      subtitle="A learning repo. Python computes; this app only draws the JSON it exports."
      pages={[
        { id: 'about', label: 'About', render: () => <AboutView state={meta} /> },
        ...(explorer
          ? [
              {
                id: 'explorer',
                label: 'Price explorer',
                render: () => (
                  <Suspense fallback={loading('price explorer')}>
                    <PriceExplorerView />
                  </Suspense>
                ),
              },
            ]
          : []),
        ...(stationarity
          ? [
              {
                id: 'stationarity',
                label: 'Stationarity',
                render: () => (
                  <Suspense fallback={loading('stationarity page')}>
                    <StationarityView />
                  </Suspense>
                ),
              },
            ]
          : []),
        ...(landscape
          ? [
              {
                id: 'landscape',
                label: 'AIC landscape',
                render: () => (
                  <Suspense fallback={loading('AIC landscape')}>
                    <AicLandscapeView />
                  </Suspense>
                ),
              },
            ]
          : []),
        ...(fit
          ? [
              {
                id: 'fit',
                label: 'Fit and diagnostics',
                render: () => (
                  <Suspense fallback={loading('fit and diagnostics page')}>
                    <FitView />
                  </Suspense>
                ),
              },
            ]
          : []),
        ...(forecast
          ? [
              {
                id: 'forecast',
                label: 'Forecast and evaluation',
                render: () => (
                  <Suspense fallback={loading('forecast and evaluation page')}>
                    <ForecastView />
                  </Suspense>
                ),
              },
            ]
          : []),
        { id: 'architecture', label: 'Architecture', render: () => <ArchitectureView /> },
      ]}
    />
  )
}

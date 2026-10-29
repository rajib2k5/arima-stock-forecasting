import { lazy, Suspense } from 'react'
import { AppShell } from './lib/shell'
import { useMeta } from './data/useMeta'
import { EXPLORER_ARTIFACTS, hasArtifacts } from './lib/gate'
import { AboutView } from './views/AboutView'
import { ArchitectureView } from './views/ArchitectureView'

const APP_SLUG = 'arima-stock-forecasting'

// A dynamic import: the explorer's code lands in its own chunk, fetched only when the page opens.
const PriceExplorerView = lazy(() => import('./views/PriceExplorerView'))

export default function App() {
  const meta = useMeta()
  // meta.json is the gate: the explorer is offered only once meta lists both files it draws.
  const explorer = meta.status === 'ready' && hasArtifacts(meta.meta, EXPLORER_ARTIFACTS)
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
                  <Suspense
                    fallback={
                      <p className="sub" role="status">
                        Loading the price explorer…
                      </p>
                    }
                  >
                    <PriceExplorerView held={meta.meta.held_artifacts} />
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

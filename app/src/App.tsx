import { AppShell } from './lib/shell'
import { useMeta } from './data/useMeta'
import { AboutView } from './views/AboutView'
import { ArchitectureView } from './views/ArchitectureView'

const APP_SLUG = 'arima-stock-forecasting'

export default function App() {
  const meta = useMeta()
  return (
    <AppShell
      slug={APP_SLUG}
      title="ARIMA stock forecasting, done carefully"
      subtitle="A learning repo. Python computes; this app only draws the JSON it exports."
      pages={[
        { id: 'about', label: 'About', render: () => <AboutView state={meta} /> },
        { id: 'architecture', label: 'Architecture', render: () => <ArchitectureView /> },
      ]}
    />
  )
}

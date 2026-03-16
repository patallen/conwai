import { useMemo } from 'react'
import { SimulationProvider, UIProvider } from './api/hooks'
import { PollingTransport } from './api/transport'
import { Shell } from './components/layout/Shell'

export default function App() {
  const dataSource = useMemo(() => new PollingTransport(1000), [])

  return (
    <SimulationProvider dataSource={dataSource}>
      <UIProvider>
        <Shell />
      </UIProvider>
    </SimulationProvider>
  )
}

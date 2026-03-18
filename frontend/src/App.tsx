import { useMemo } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { SimulationProvider, ControlPanelProvider } from './api/hooks'
import { PollingTransport } from './api/transport'
import { Shell } from './components/layout/Shell'

export default function App() {
  const dataSource = useMemo(() => new PollingTransport(1000), [])

  return (
    <BrowserRouter>
      <SimulationProvider dataSource={dataSource}>
        <ControlPanelProvider>
          <Shell />
        </ControlPanelProvider>
      </SimulationProvider>
    </BrowserRouter>
  )
}

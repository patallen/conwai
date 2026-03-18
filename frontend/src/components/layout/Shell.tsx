import { useControlPanel, useControlPanelDispatch } from '../../api/hooks'
import { Sidebar } from './Sidebar'
import { MainView } from './MainView'
import { ControlPanel } from '../controls/ControlPanel'

export function Shell() {
  const { controlPanelOpen } = useControlPanel()
  const cpDispatch = useControlPanelDispatch()

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `240px 1fr${controlPanelOpen ? ' 320px' : ''}`,
      gridTemplateRows: '1fr',
      height: '100vh',
      gap: 0,
    }}>
      <div style={{
        borderRight: '1px solid var(--border)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <Sidebar />
      </div>

      <div style={{ overflow: 'hidden', position: 'relative', minWidth: 0 }}>
        <MainView />
      </div>

      {controlPanelOpen && (
        <div style={{
          borderLeft: '1px solid var(--border)',
          overflow: 'auto',
        }}>
          <ControlPanel />
        </div>
      )}

      {!controlPanelOpen && (
        <button
          onClick={() => cpDispatch({ type: 'TOGGLE_CONTROL_PANEL' })}
          style={{
            position: 'fixed', right: 16, top: 16, zIndex: 50,
            background: 'var(--bg-surface)', border: '1px solid var(--accent)',
            borderRadius: 6, padding: '6px 12px',
            color: 'var(--accent)', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
          }}
        >
          HANDLER
        </button>
      )}
    </div>
  )
}

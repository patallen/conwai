import { useUIDispatch } from '../../api/hooks'

interface ContextMenuProps {
  handle: string
  x: number
  y: number
  onClose: () => void
}

export function ContextMenu({ handle, x, y, onClose }: ContextMenuProps) {
  const dispatch = useUIDispatch()

  const items = [
    { label: 'View Detail', action: () => dispatch({ type: 'SELECT_AGENT', handle }) },
    { label: 'Send DM', action: () => dispatch({ type: 'OPEN_CONTROL_PANEL', prefill: { action: 'send_dm', to: handle } as any }) },
    { label: 'Adjust Energy', action: () => dispatch({ type: 'OPEN_CONTROL_PANEL', prefill: { action: 'set_energy', handle } as any }) },
  ]

  return (
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 99 }}
      />
      <div style={{
        position: 'fixed', left: x, top: y, zIndex: 100,
        background: '#1a1b26', border: '1px solid var(--border)',
        borderRadius: 6, padding: 4, minWidth: 140,
        boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
      }}>
        {items.map(item => (
          <div
            key={item.label}
            onClick={() => { item.action(); onClose() }}
            style={{
              padding: '6px 10px', cursor: 'pointer', borderRadius: 4,
              fontSize: 11, fontFamily: 'var(--font-mono)',
              color: 'var(--text-primary)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-surface)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            {item.label}
          </div>
        ))}
      </div>
    </>
  )
}

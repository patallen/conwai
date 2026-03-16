import { useState, useEffect } from 'react'
import { useSimulation, useUIState, useUIDispatch, useSendAction } from '../../api/hooks'
import type { HandlerAction } from '../../api/types'

type ActionType = HandlerAction['action']

export function ControlPanel() {
  const { agents } = useSimulation()
  const { controlPanelPrefill } = useUIState()
  const dispatch = useUIDispatch()
  const sendAction = useSendAction()

  const [activeAction, setActiveAction] = useState<ActionType>('post_board')
  const [content, setContent] = useState('')
  const [targetHandle, setTargetHandle] = useState('')
  const [energyValue, setEnergyValue] = useState(0)
  const [confirming, setConfirming] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; error?: string } | null>(null)

  // Handle prefill from contextual actions
  useEffect(() => {
    if (controlPanelPrefill) {
      const p = controlPanelPrefill as any
      if (p.action) setActiveAction(p.action)
      if (p.to) setTargetHandle(p.to)
      if (p.handle) setTargetHandle(p.handle)
      if (p.content) setContent(p.content)
    }
  }, [controlPanelPrefill])

  function buildAction(): HandlerAction | null {
    switch (activeAction) {
      case 'post_board': return content ? { action: 'post_board', content } : null
      case 'send_dm': return content && targetHandle ? { action: 'send_dm', to: targetHandle, content } : null
      case 'set_energy': return targetHandle ? { action: 'set_energy', handle: targetHandle, value: energyValue } : null
      case 'drain_energy': return targetHandle ? { action: 'drain_energy', handle: targetHandle, amount: energyValue } : null
      case 'drop_secret': return content && targetHandle ? { action: 'drop_secret', handle: targetHandle, content } : null
      default: return null
    }
  }

  function describeAction(): string {
    switch (activeAction) {
      case 'post_board': return `Post to board: "${content.slice(0, 50)}"`
      case 'send_dm': return `DM ${targetHandle}: "${content.slice(0, 50)}"`
      case 'set_energy': return `Set ${targetHandle} energy to ${energyValue}`
      case 'drain_energy': return `Drain ${energyValue} energy from ${targetHandle}`
      case 'drop_secret': return `Drop secret to ${targetHandle}: "${content.slice(0, 50)}"`
      default: return ''
    }
  }

  async function execute() {
    const action = buildAction()
    if (!action) return
    const res = await sendAction(action)
    setResult(res)
    setConfirming(false)
    if (res.ok) {
      setContent('')
      setTargetHandle('')
      setEnergyValue(0)
      setTimeout(() => setResult(null), 2000)
    }
  }

  const currentAction = buildAction()
  const needsTarget = activeAction !== 'post_board'
  const needsContent = ['post_board', 'send_dm', 'drop_secret'].includes(activeAction)
  const needsEnergy = ['set_energy', 'drain_energy'].includes(activeAction)

  const actions: { value: ActionType; label: string }[] = [
    { value: 'post_board', label: 'Post to Board' },
    { value: 'send_dm', label: 'Send DM' },
    { value: 'set_energy', label: 'Set Energy' },
    { value: 'drain_energy', label: 'Drain Energy' },
    { value: 'drop_secret', label: 'Drop Secret' },
  ]

  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'rgba(255,255,255,0.03)',
    border: '1px solid var(--border)', borderRadius: 4,
    padding: '6px 10px', color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)', fontSize: 12,
    outline: 'none',
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: 'var(--accent)', fontWeight: 600, fontSize: 13, letterSpacing: 0.5 }}>HANDLER</span>
        <span
          onClick={() => dispatch({ type: 'CLOSE_CONTROL_PANEL' })}
          style={{ color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 18 }}
        >
          ×
        </span>
      </div>

      {/* Action selector */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {actions.map(a => (
          <button
            key={a.value}
            onClick={() => { setActiveAction(a.value); setConfirming(false); setResult(null) }}
            style={{
              background: activeAction === a.value ? 'var(--bg-surface)' : 'transparent',
              border: `1px solid ${activeAction === a.value ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 4, padding: '3px 8px',
              color: activeAction === a.value ? 'var(--accent)' : 'var(--text-secondary)',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10,
            }}
          >
            {a.label}
          </button>
        ))}
      </div>

      {/* Target selector */}
      {needsTarget && (
        <div>
          <label style={{ color: 'var(--text-secondary)', fontSize: 10, display: 'block', marginBottom: 4 }}>Agent</label>
          <select
            value={targetHandle}
            onChange={e => setTargetHandle(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}
          >
            <option value="">Select agent...</option>
            {agents.map(a => (
              <option key={a.handle} value={a.handle}>{a.handle} ({a.personality})</option>
            ))}
          </select>
        </div>
      )}

      {/* Content input */}
      {needsContent && (
        <div>
          <label style={{ color: 'var(--text-secondary)', fontSize: 10, display: 'block', marginBottom: 4 }}>
            {activeAction === 'drop_secret' ? 'Secret' : 'Message'}
          </label>
          <textarea
            value={content}
            onChange={e => setContent(e.target.value)}
            placeholder={activeAction === 'drop_secret' ? 'Secret text...' : 'Message...'}
            rows={3}
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </div>
      )}

      {/* Energy input */}
      {needsEnergy && (
        <div>
          <label style={{ color: 'var(--text-secondary)', fontSize: 10, display: 'block', marginBottom: 4 }}>
            {activeAction === 'set_energy' ? 'New value' : 'Amount to drain'}
          </label>
          <input
            type="number"
            value={energyValue}
            onChange={e => setEnergyValue(parseInt(e.target.value) || 0)}
            style={inputStyle}
          />
        </div>
      )}

      {/* Confirm / Execute */}
      {confirming ? (
        <div style={{
          background: 'rgba(250,204,21,0.08)', border: '1px solid rgba(250,204,21,0.2)',
          borderRadius: 4, padding: 8, fontSize: 11,
        }}>
          <div style={{ color: '#facc15', marginBottom: 6 }}>{describeAction()}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={execute} style={{
              background: 'var(--accent)', border: 'none', borderRadius: 4,
              padding: '4px 12px', color: '#0f1117', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
            }}>
              Confirm
            </button>
            <button onClick={() => setConfirming(false)} style={{
              background: 'transparent', border: '1px solid var(--border)', borderRadius: 4,
              padding: '4px 12px', color: 'var(--text-secondary)', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 11,
            }}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => currentAction && setConfirming(true)}
          disabled={!currentAction}
          style={{
            background: currentAction ? 'var(--bg-surface)' : 'transparent',
            border: `1px solid ${currentAction ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: 4, padding: '6px 12px',
            color: currentAction ? 'var(--accent)' : 'var(--text-secondary)',
            cursor: currentAction ? 'pointer' : 'default',
            fontFamily: 'var(--font-mono)', fontSize: 11,
          }}
        >
          Preview Action
        </button>
      )}

      {/* Result */}
      {result && (
        <div style={{
          fontSize: 11, padding: 6, borderRadius: 4,
          color: result.ok ? 'var(--energy-healthy)' : 'var(--energy-critical)',
          background: result.ok ? 'rgba(52,211,153,0.08)' : 'rgba(239,68,68,0.08)',
        }}>
          {result.ok ? 'Sent!' : `Error: ${result.error}`}
        </div>
      )}
    </div>
  )
}

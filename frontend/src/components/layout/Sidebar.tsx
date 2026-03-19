import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { AgentCard } from '../agents/AgentCard'

export function Sidebar() {
  const data = useSimulation()
  const { agents, events, tick, aliveCount, totalEvents } = data
  const { selectedAgent, view } = useUIState()
  const dispatch = useUIDispatch()

  const maxEnergy = agents.reduce((max, a) => Math.max(max, a.energy ?? 0), 0)
  const sorted = [...agents].sort((a, b) => (b.energy ?? 0) - (a.energy ?? 0))

  const navLinkStyle = (active: boolean) => ({
    padding: '6px 16px',
    cursor: 'pointer',
    fontSize: 12,
    fontFamily: 'var(--font-mono)' as const,
    fontWeight: 600 as const,
    color: active ? 'var(--accent)' : 'var(--text-secondary)',
    background: active ? 'rgba(129,140,248,0.08)' : 'transparent',
    borderBottom: '1px solid var(--border)',
  })

  return (
    <>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span
          onClick={() => dispatch({ type: 'SHOW_GRAPH' })}
          style={{
            color: 'var(--accent)', fontWeight: 600, fontSize: 15,
            letterSpacing: 1, cursor: 'pointer',
          }}
        >
          CONWAI
        </span>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
        <div onClick={() => dispatch({ type: 'SHOW_BOARD' })} style={navLinkStyle(view === 'board')}>
          BOARD
        </div>
        <div onClick={() => dispatch({ type: 'SHOW_ECONOMY' })} style={navLinkStyle(view === 'economy')}>
          ECONOMY
        </div>
      </div>

      {data.cipher && (
        <div style={{
          padding: '8px 16px',
          borderBottom: '1px solid var(--border)',
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
        }}>
          <div style={{ color: 'var(--accent)', fontWeight: 600, marginBottom: 4 }}>
            CIPHER ACTIVE
          </div>
          <div style={{
            color: 'var(--text-primary)',
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: 1.5,
            wordBreak: 'break-all',
            marginBottom: 6,
          }}>
            {data.cipher.ciphertext}
          </div>
          <div style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <div>clues: {data.cipher.clue_holders.join(', ')}</div>
            <div>reward: {data.cipher.reward} · penalty: {data.cipher.penalty}</div>
            <div>expires tick {data.cipher.expires_tick} ({data.cipher.expires_tick - tick} left)</div>
          </div>
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {sorted.map(agent => (
          <AgentCard
            key={agent.handle}
            agent={agent}
            events={events}
            maxEnergy={maxEnergy}
            selected={selectedAgent === agent.handle}
            onClick={() => dispatch({ type: 'SELECT_AGENT', handle: agent.handle })}
          />
        ))}
      </div>

      <div style={{
        padding: '8px 16px',
        borderTop: '1px solid var(--border)',
        display: 'flex', gap: 12,
        color: 'var(--text-secondary)', fontSize: 11,
        fontFamily: 'var(--font-mono)',
      }}>
        <span>tick {tick}</span>
        <span>{aliveCount} alive</span>
        <span>{totalEvents} events</span>
      </div>
    </>
  )
}

import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { AgentCard } from '../agents/AgentCard'

export function Sidebar() {
  const { agents, events, tick, aliveCount, totalEvents } = useSimulation()
  const { selectedAgent } = useUIState()
  const dispatch = useUIDispatch()

  const maxEnergy = agents.reduce((max, a) => Math.max(max, a.energy ?? 0), 0)
  const sorted = [...agents].sort((a, b) => (b.energy ?? 0) - (a.energy ?? 0))

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

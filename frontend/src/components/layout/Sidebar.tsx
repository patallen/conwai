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

      {data.cipher && (() => {
        const parseClue = (clue: string) => {
          const m = clue.match(/'([A-Z])' decodes to '([A-Z])'/)
          return m ? `${m[1]}→${m[2]}` : clue
        }
        return (
          <div style={{
            padding: '8px 16px',
            borderBottom: '1px solid var(--border)',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
          }}>
            <div style={{ color: 'var(--accent)', fontWeight: 600, marginBottom: 4 }}>
              CIPHER · {data.cipher.expires_tick - tick} ticks left
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
            <div style={{ color: 'var(--text-secondary)', lineHeight: 1.4, marginBottom: 4 }}>
              {data.cipher.clue_holders.map(h => (
                <span key={h} style={{ marginRight: 8 }}>{h}:{parseClue(data.cipher!.clues[h])}</span>
              ))}
            </div>
            {data.cipher.attempts.length > 0 && (
              <div style={{ marginTop: 4, borderTop: '1px solid var(--border)', paddingTop: 4 }}>
                <div style={{ color: 'var(--text-secondary)', marginBottom: 2 }}>ATTEMPTS</div>
                {data.cipher.attempts.map((a, i) => (
                  <div key={i} style={{ color: '#ef4444' }}>
                    {a.handle}: "{a.guess}" ({a.correct_chars}/{data.cipher!.ciphertext.replace(/ /g, '').length})
                  </div>
                ))}
              </div>
            )}
            <div style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
              reward: {data.cipher.reward} · penalty: {data.cipher.penalty}
            </div>
          </div>
        )
      })()}

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

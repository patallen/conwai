import { useState, useEffect } from 'react'
import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

export function AgentDetail() {
  const { agents, events, stats, conversations, tick } = useSimulation()
  const { selectedAgent } = useUIState()
  const dispatch = useUIDispatch()
  const [context, setContext] = useState<any>(null)
  const [contextLoading, setContextLoading] = useState(false)
  const [compactedMemory, setCompactedMemory] = useState<string>('')

  const agent = agents.find(a => a.handle === selectedAgent)
  const agentStats = stats.find(s => s.handle === selectedAgent)
  const color = selectedAgent ? getAgentColor(selectedAgent) : 'var(--text-primary)'

  // Agent's recent events
  const agentEvents = events
    .filter(e => e.entity === selectedAgent || (e.type === 'dm_sent' && e.data.to === selectedAgent))
    .slice(-50)

  const boardPosts = agentEvents.filter(e => e.type === 'board_post').slice(-10)
  const dms = agentEvents.filter(e => e.type === 'dm_sent').slice(-20)

  // Trade history: gives where this agent is sender or receiver
  const gives = events.filter(e =>
    e.type === 'give' && (e.entity === selectedAgent || e.data.to === selectedAgent)
  ).slice(-30)

  // Trading partners summary
  const partnerCounts: Record<string, number> = {}
  for (const g of gives) {
    const partner = g.entity === selectedAgent ? g.data.to : g.entity
    if (partner) partnerCounts[partner] = (partnerCounts[partner] || 0) + 1
  }
  const topPartners = Object.entries(partnerCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)

  // Conversations involving this agent
  const agentConvos = Object.entries(conversations)
    .filter(([key]) => key.split('-').includes(selectedAgent ?? ''))

  async function loadContext() {
    if (!selectedAgent) return
    setContextLoading(true)
    try {
      const resp = await fetch(`/api/agent/${selectedAgent}/context`)
      const data = await resp.json()
      if (!data.error) setContext(data)
      else setContext(null)
    } catch { setContext(null) }
    setContextLoading(false)
  }

  // Reset context when agent changes
  useEffect(() => { setContext(null) }, [selectedAgent])

  // Auto-fetch compacted memory
  useEffect(() => {
    if (!selectedAgent) return
    setCompactedMemory('')
    const fetchMemory = async () => {
      try {
        const resp = await fetch(`/api/agent/${selectedAgent}/memory`)
        const data = await resp.json()
        if (data.memory) setCompactedMemory(data.memory)
      } catch { /* ignore */ }
    }
    fetchMemory()
    const interval = setInterval(fetchMemory, 5000)
    return () => clearInterval(interval)
  }, [selectedAgent])

  if (!agent) {
    return <div style={{ padding: 16, color: 'var(--text-secondary)' }}>Agent not found</div>
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden', padding: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <span style={{
          fontSize: 20, fontWeight: 700, color, fontFamily: 'var(--font-mono)',
        }}>
          {agent.handle}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{agent.role} · {agent.personality} · age {tick - agent.born_tick} ticks</span>
        <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)', fontSize: 12, display: 'flex', gap: 12 }}>
          <span>coins: <span style={{ color: 'var(--text-primary)' }}>{agent.energy ?? '?'}</span></span>
          <span>hunger: <span style={{ color: 'var(--text-primary)' }}>{agent.hunger ?? '?'}/100</span></span>
          <span>thirst: <span style={{ color: 'var(--text-primary)' }}>{agent.thirst ?? '?'}/100</span></span>
          <span>flour: <span style={{ color: '#c8a' }}>{agent.flour}</span></span>
          <span>water: <span style={{ color: '#48c' }}>{agent.water}</span></span>
          <span>bread: <span style={{ color: '#ca4' }}>{agent.bread}</span></span>
        </span>
        <button
          onClick={() => dispatch({ type: 'OPEN_CONTROL_PANEL', prefill: { action: 'send_dm', to: agent.handle } as any })}
          style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 4, padding: '4px 10px', color: 'var(--accent)',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
          }}
        >
          Send DM
        </button>
      </div>

      {/* Stats */}
      {agentStats && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 12 }}>
          <span style={{ color: 'var(--text-secondary)' }}>posts: <span style={{ color: 'var(--text-primary)' }}>{agentStats.posts}</span></span>
          <span style={{ color: 'var(--text-secondary)' }}>dms sent: <span style={{ color: 'var(--text-primary)' }}>{agentStats.dms_sent}</span></span>
          <span style={{ color: 'var(--text-secondary)' }}>dms recv: <span style={{ color: 'var(--text-primary)' }}>{agentStats.dms_received}</span></span>
          <span style={{ color: 'var(--text-secondary)' }}>remembers: <span style={{ color: 'var(--text-primary)' }}>{agentStats.remembers}</span></span>
        </div>
      )}

      {/* Trading Partners */}
      <Section title={`trading partners (${topPartners.length})`}>
        {topPartners.length === 0 ? <Muted>(none)</Muted> : topPartners.map(([partner, count]) => (
          <div key={partner} style={{
            padding: '3px 0', fontSize: 12, display: 'flex', justifyContent: 'space-between',
            borderBottom: '1px solid var(--border)',
          }}>
            <span
              style={{ color: getAgentColor(partner), cursor: 'pointer' }}
              onClick={() => dispatch({ type: 'SELECT_AGENT', handle: partner })}
            >
              {partner}
            </span>
            <span style={{ color: 'var(--text-secondary)' }}>{count} trades</span>
          </div>
        ))}
      </Section>

      {/* Trade History */}
      <Section title={`trade history (${gives.length})`}>
        {gives.length === 0 ? <Muted>(none)</Muted> : gives.slice().reverse().map((e, i) => {
          const outgoing = e.entity === selectedAgent
          const partner = outgoing ? e.data.to : e.entity
          const item = e.data.resource && e.data.amount
            ? `${e.data.amount} ${e.data.resource}`
            : ''
          return (
            <div key={`give-${e.idx}-${i}`} style={{
              padding: '3px 0', borderBottom: '1px solid var(--border)', fontSize: 12,
            }}>
              <span style={{ color: outgoing ? '#f97316' : '#34d399' }}>
                {outgoing ? 'sent' : 'recv'}
              </span>
              {' '}
              <span
                style={{ color: getAgentColor(partner), cursor: 'pointer' }}
                onClick={() => dispatch({ type: 'SELECT_AGENT', handle: partner })}
              >
                {outgoing ? `-> ${partner}` : `<- ${partner}`}
              </span>
              {item && (
                <span style={{ color: 'var(--text-secondary)' }}> {item}</span>
              )}
            </div>
          )
        })}
      </Section>

      {/* Soul */}
      <Section title="soul">
        <div style={{ color: '#67e8f9', fontStyle: 'italic', fontSize: 12 }}>
          {agent.soul || '(empty)'}
        </div>
      </Section>

      {/* Compacted Memory */}
      <Section title="compacted memory">
        <pre style={{ color: 'var(--text-primary)', fontSize: 12, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>
          {compactedMemory || '(not yet compacted)'}
        </pre>
      </Section>

      {/* Memory */}
      <Section title="memory">
        <div style={{ color: 'var(--text-primary)', fontSize: 12 }}>
          {agent.memory || '(empty)'}
        </div>
      </Section>

      {/* Recent Board Posts */}
      <Section title={`recent posts (${boardPosts.length})`}>
        {boardPosts.length === 0 ? <Muted>(none)</Muted> : boardPosts.map((e, i) => (
          <div key={`post-${e.idx}-${i}`} style={{ padding: '4px 0', borderBottom: '1px solid var(--border)', fontSize: 12, overflowWrap: 'anywhere' }}>
            {e.data.content}
          </div>
        ))}
      </Section>

      {/* Recent DMs */}
      <Section title={`recent DMs (${dms.length})`}>
        {dms.length === 0 ? <Muted>(none)</Muted> : dms.map((e, i) => {
          const outgoing = e.entity === selectedAgent
          return (
            <div key={`dm-${e.idx}-${i}`} style={{ padding: '4px 0', borderBottom: '1px solid var(--border)', fontSize: 12, overflowWrap: 'anywhere' }}>
              <span style={{ color: outgoing ? 'var(--energy-healthy)' : 'var(--accent-interactive)' }}>
                {outgoing ? `→ ${e.data.to}` : `← ${e.entity}`}
              </span>
              {': '}{e.data.content}
            </div>
          )
        })}
      </Section>

      {/* Conversations */}
      <Section title={`conversations (${agentConvos.length})`}>
        {agentConvos.map(([key, msgs]) => (
          <div
            key={key}
            onClick={() => dispatch({ type: 'SELECT_CONVERSATION', key })}
            style={{
              padding: '6px 0', cursor: 'pointer', borderBottom: '1px solid var(--border)',
              fontSize: 12, color: 'var(--accent-interactive)',
            }}
          >
            {key} ({msgs.length} messages)
          </div>
        ))}
      </Section>

      {/* Context */}
      <Section title="LLM context">
        {context ? (
          <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>
            <div style={{ color: 'var(--energy-healthy)', marginBottom: 8, fontWeight: 600 }}>SYSTEM PROMPT</div>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: 'var(--text-primary)', marginBottom: 16, maxHeight: 300, overflow: 'auto' }}>
              {context.system}
            </pre>
            <div style={{ color: 'var(--energy-healthy)', marginBottom: 8, fontWeight: 600 }}>
              MESSAGES ({context.messages?.length ?? 0})
            </div>
            {context.messages?.map((m: any, i: number) => (
              <div key={i} style={{
                background: m.role === 'user' ? 'rgba(129,140,248,0.08)' : m.role === 'assistant' ? 'rgba(167,139,250,0.08)' : 'rgba(250,204,21,0.08)',
                border: '1px solid var(--border)', borderRadius: 4, padding: 8, marginBottom: 4,
              }}>
                <div style={{ color: m.role === 'user' ? '#818cf8' : m.role === 'assistant' ? '#a78bfa' : '#facc15', fontWeight: 600, marginBottom: 4 }}>
                  {m.role}{m.name ? ` (${m.name})` : ''}
                </div>
                <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: 'var(--text-primary)', maxHeight: 200, overflow: 'auto' }}>
                  {m.content ?? ''}
                  {m.tool_calls?.map((tc: any) => `\n[tool_call] ${tc.function.name}(${tc.function.arguments})`).join('') ?? ''}
                </pre>
              </div>
            ))}
          </div>
        ) : (
          <button
            onClick={loadContext}
            disabled={contextLoading}
            style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '4px 12px', color: 'var(--accent)',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
            }}
          >
            {contextLoading ? 'Loading...' : 'Load Context'}
          </button>
        )}
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16, overflow: 'hidden' }}>
      <div style={{ color: 'var(--energy-healthy)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
        {title}
      </div>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 4, padding: 10, maxHeight: 300, overflowY: 'auto',
        overflowWrap: 'anywhere',
      }}>
        {children}
      </div>
    </div>
  )
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>{children}</span>
}

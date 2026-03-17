import { useState } from 'react'
import type { Agent, SimEvent } from '../../api/types'
import { getAgentColor } from '../../api/colors'
import { ContextMenu } from '../controls/ContextMenu'

const RECENCY_WINDOW_MS = 10_000

interface AgentCardProps {
  agent: Agent
  events: SimEvent[]
  maxEnergy: number
  selected: boolean
  onClick: () => void
}

export function AgentCard({ agent, events, maxEnergy, selected, onClick }: AgentCardProps) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const color = getAgentColor(agent.handle)
  const energyPct = agent.energy != null && maxEnergy > 0
    ? Math.round((agent.energy / maxEnergy) * 100)
    : 0
  const now = Date.now() / 1000
  const recentlyActive = events.some(
    e => e.entity === agent.handle && (now - e.t) < RECENCY_WINDOW_MS / 1000
  )

  const hungerPct = agent.hunger != null ? Math.round(agent.hunger) : 0
  const energyColor = energyPct < 20
    ? 'var(--energy-critical)'
    : energyPct < 50
    ? 'var(--energy-warning)'
    : 'var(--energy-healthy)'
  const hungerColor = hungerPct < 20
    ? 'var(--energy-critical)'
    : hungerPct < 50
    ? 'var(--energy-warning)'
    : '#4a9'

  return (
    <div
      onClick={onClick}
      onContextMenu={e => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}
      style={{
        padding: '8px 12px',
        borderLeft: `2px solid ${selected ? color : 'transparent'}`,
        background: selected ? 'var(--bg-surface)' : 'transparent',
        cursor: 'pointer',
        transition: 'background 200ms, border-color 200ms',
      }}
      onMouseEnter={e => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-surface-hover)'
      }}
      onMouseLeave={e => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background = 'transparent'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {recentlyActive && (
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: color, boxShadow: `0 0 6px ${color}`,
            animation: 'pulse 2s ease-in-out infinite',
          }} />
        )}
        <span style={{ color, fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12 }}>
          {agent.handle}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 11, marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <span>{agent.energy != null ? agent.energy : '?'}c</span>
          <span style={{ color: hungerColor }}>{agent.hunger != null ? agent.hunger : '?'}h</span>
          <span style={{ color: 'var(--text-secondary)' }}>{agent.food != null ? agent.food : '?'}f</span>
        </span>
      </div>
      <div style={{ display: 'flex', gap: 2, margin: '4px 0' }}>
        <div style={{
          background: 'rgba(255,255,255,0.05)', height: 3, borderRadius: 2, flex: 1,
        }}>
          <div style={{
            height: '100%', borderRadius: 2, width: `${energyPct}%`,
            background: energyColor,
            boxShadow: `0 0 6px ${energyColor}40`,
            transition: 'width 300ms ease',
          }} />
        </div>
        <div style={{
          background: 'rgba(255,255,255,0.05)', height: 3, borderRadius: 2, flex: 1,
        }}>
          <div style={{
            height: '100%', borderRadius: 2, width: `${hungerPct}%`,
            background: hungerColor,
            boxShadow: `0 0 6px ${hungerColor}40`,
            transition: 'width 300ms ease',
          }} />
        </div>
      </div>
      <div style={{ color: 'var(--text-secondary)', fontSize: 10 }}>
        {agent.personality}
      </div>
      {menu && <ContextMenu handle={agent.handle} x={menu.x} y={menu.y} onClose={() => setMenu(null)} />}
    </div>
  )
}

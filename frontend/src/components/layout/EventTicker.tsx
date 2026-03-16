import { useSimulation } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

const TYPE_COLORS: Record<string, string> = {
  board_post: '#34d399',
  dm_sent: '#818cf8',
  inspect: '#64748b',
  remember: '#facc15',
  soul_updated: '#67e8f9',
  secret_dropped: '#f87171',
  question_posted: '#a78bfa',
  code_submitted: '#fb923c',
  code_solved: '#4ade80',
  code_wrong_guess: '#f97316',
}

function eventContent(e: { type: string; entity: string; data: Record<string, any> }): string {
  if (e.type === 'dm_sent') return `→ ${e.data.to}: ${e.data.content ?? ''}`
  if (e.type === 'board_post') return e.data.content ?? ''
  if (e.type === 'inspect') return `inspected ${e.data.target ?? '?'}`
  if (e.type === 'code_submitted') return `submitted ${e.data.guess ?? '?'}`
  if (e.type === 'code_solved') return `solved!`
  return e.data.content ?? e.data.secret ?? e.data.question ?? ''
}

export function EventTicker() {
  const { events } = useSimulation()
  const recent = events
    .filter(e => e.type !== 'sleeping' && e.type !== 'no_energy')
    .slice(-30)

  return (
    <div style={{
      height: '100%', overflowX: 'auto', overflowY: 'hidden',
      display: 'flex', alignItems: 'center', gap: 16,
      padding: '0 16px', whiteSpace: 'nowrap',
      fontFamily: 'var(--font-mono)', fontSize: 11,
    }}>
      {recent.map(e => (
        <span key={e.idx} style={{ display: 'inline-flex', gap: 4, flexShrink: 0 }}>
          <span style={{ color: getAgentColor(e.entity) }}>{e.entity}</span>
          <span style={{ color: TYPE_COLORS[e.type] ?? 'var(--text-secondary)' }}>{e.type}</span>
          <span style={{ color: 'var(--text-secondary)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {eventContent(e).slice(0, 80)}
          </span>
        </span>
      ))}
    </div>
  )
}

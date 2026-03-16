import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

export function ConversationView() {
  const { conversations } = useSimulation()
  const { selectedConversation } = useUIState()
  const dispatch = useUIDispatch()

  if (!selectedConversation) {
    return <div style={{ padding: 16, color: 'var(--text-secondary)' }}>No conversation selected</div>
  }

  const messages = conversations[selectedConversation] ?? []
  const [handleA, handleB] = selectedConversation.split('-')
  const colorA = getAgentColor(handleA)
  const colorB = getAgentColor(handleB)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '12px 20px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span
          onClick={() => dispatch({ type: 'SELECT_AGENT', handle: handleA })}
          style={{ color: colorA, fontFamily: 'var(--font-mono)', fontWeight: 600, cursor: 'pointer' }}
        >
          {handleA}
        </span>
        <span style={{ color: 'var(--text-secondary)' }}>↔</span>
        <span
          onClick={() => dispatch({ type: 'SELECT_AGENT', handle: handleB })}
          style={{ color: colorB, fontFamily: 'var(--font-mono)', fontWeight: 600, cursor: 'pointer' }}
        >
          {handleB}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 11, marginLeft: 'auto' }}>
          {messages.length} messages
        </span>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px' }}>
        {messages.map(msg => {
          const isA = msg.entity === handleA
          const color = isA ? colorA : colorB
          return (
            <div key={msg.idx} style={{
              display: 'flex', flexDirection: 'column',
              alignItems: isA ? 'flex-start' : 'flex-end',
              marginBottom: 8,
            }}>
              <span style={{ color, fontFamily: 'var(--font-mono)', fontSize: 10, marginBottom: 2 }}>
                {msg.entity}
              </span>
              <div style={{
                background: isA ? 'rgba(129,140,248,0.08)' : 'rgba(167,139,250,0.08)',
                border: '1px solid var(--border)', borderRadius: 6,
                padding: '6px 10px', maxWidth: '70%', fontSize: 12,
              }}>
                {msg.data.content}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

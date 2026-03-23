import { useSimulation, useUIDispatch } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

function formatTime(t: number): string {
  const d = new Date(t * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function BoardView() {
  const { board } = useSimulation()
  const dispatch = useUIDispatch()

  // Show newest first
  const posts = [...board].reverse()

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: 24 }}>
      <div style={{
        fontSize: 16, fontWeight: 700, color: 'var(--accent)',
        fontFamily: 'var(--font-mono)', marginBottom: 20, letterSpacing: 1,
      }}>
        BOARD ({posts.length} posts)
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {posts.map(post => (
          <div key={post.idx} style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            padding: '10px 14px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span
                onClick={() => dispatch({ type: 'SELECT_AGENT', handle: post.entity })}
                style={{
                  color: getAgentColor(post.entity),
                  fontWeight: 600,
                  fontSize: 13,
                  fontFamily: 'var(--font-mono)',
                  cursor: 'pointer',
                }}
              >
                {post.entity}
              </span>
              <span style={{ color: 'var(--text-secondary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                {formatTime(post.t)}
              </span>
            </div>
            <div style={{
              color: 'var(--text-primary)',
              fontSize: 13,
              lineHeight: 1.5,
              overflowWrap: 'anywhere',
            }}>
              {post.data.message}
            </div>
          </div>
        ))}

        {posts.length === 0 && (
          <div style={{ color: 'var(--text-secondary)', fontStyle: 'italic', fontSize: 13 }}>
            No board posts yet.
          </div>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useRef } from 'react'
import { useSendAction } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

interface InboxMessage {
  t: number
  content: string
}

interface ThreadMessage {
  from: string
  to: string
  content: string
  t: number
}

export function HandlerInbox() {
  const sendAction = useSendAction()

  const [threads, setThreads] = useState<Record<string, InboxMessage[]>>({})
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null)
  const [threadMessages, setThreadMessages] = useState<ThreadMessage[]>([])
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Poll inbox threads
  useEffect(() => {
    const poll = async () => {
      try {
        const resp = await fetch('/api/handler/inbox')
        setThreads(await resp.json())
      } catch (err) {
        console.warn('Inbox poll failed:', err)
      }
    }
    poll()
    const id = setInterval(poll, 3000)
    return () => clearInterval(id)
  }, [])

  // Poll selected thread
  useEffect(() => {
    if (!selectedHandle) { setThreadMessages([]); return }
    const poll = async () => {
      try {
        const resp = await fetch(`/api/handler/inbox/${selectedHandle}`)
        setThreadMessages(await resp.json())
      } catch (err) {
        console.warn('Thread poll failed:', err)
      }
    }
    poll()
    const id = setInterval(poll, 3000)
    return () => clearInterval(id)
  }, [selectedHandle])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [threadMessages])

  const handleSend = async () => {
    if (!selectedHandle || !reply.trim() || sending) return
    setSending(true)
    try {
      await sendAction({ action: 'send_dm', to: selectedHandle, content: reply.trim() })
      setReply('')
      // Immediately re-fetch thread
      const resp = await fetch(`/api/handler/inbox/${selectedHandle}`)
      setThreadMessages(await resp.json())
    } catch (err) {
      console.warn('Send failed:', err)
    } finally {
      setSending(false)
    }
  }

  const sortedHandles = Object.entries(threads)
    .sort(([, a], [, b]) => {
      const lastA = a.length > 0 ? a[a.length - 1].t : 0
      const lastB = b.length > 0 ? b[b.length - 1].t : 0
      return lastB - lastA
    })
    .map(([handle]) => handle)

  return (
    <div style={{ height: '100%', display: 'flex' }}>
      {/* Left panel: thread list */}
      <div style={{
        width: 260, minWidth: 260, borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        <div style={{
          padding: '12px 16px', borderBottom: '1px solid var(--border)',
          color: 'var(--accent)', fontWeight: 600, fontSize: 13,
          fontFamily: 'var(--font-mono)', letterSpacing: 0.5,
        }}>
          INBOX
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {sortedHandles.length === 0 && (
            <div style={{
              padding: '20px 16px', color: 'var(--text-secondary)',
              fontSize: 12, fontFamily: 'var(--font-mono)',
            }}>
              No messages yet
            </div>
          )}
          {sortedHandles.map(handle => {
            const msgs = threads[handle]
            const lastMsg = msgs[msgs.length - 1]
            const isSelected = selectedHandle === handle
            const color = getAgentColor(handle)
            return (
              <div
                key={handle}
                onClick={() => setSelectedHandle(handle)}
                style={{
                  padding: '10px 16px', cursor: 'pointer',
                  borderBottom: '1px solid var(--border)',
                  background: isSelected ? 'rgba(129,140,248,0.08)' : 'transparent',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{
                    color, fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12,
                  }}>
                    {handle}
                  </span>
                  <span style={{
                    color: 'var(--text-secondary)', fontSize: 10, fontFamily: 'var(--font-mono)',
                  }}>
                    {msgs.length}
                  </span>
                </div>
                {lastMsg && (
                  <div style={{
                    color: 'var(--text-secondary)', fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {lastMsg.content}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Right panel: thread view */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {!selectedHandle ? (
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'var(--font-mono)',
          }}>
            Select a thread
          </div>
        ) : (
          <>
            {/* Thread header */}
            <div style={{
              padding: '12px 20px', borderBottom: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <span style={{
                color: getAgentColor(selectedHandle),
                fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 13,
              }}>
                {selectedHandle}
              </span>
              <span style={{ color: 'var(--text-secondary)' }}>
                ↔
              </span>
              <span style={{
                color: 'var(--accent)',
                fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 13,
              }}>
                HANDLER
              </span>
              <span style={{
                color: 'var(--text-secondary)', fontSize: 11,
                fontFamily: 'var(--font-mono)', marginLeft: 'auto',
              }}>
                {threadMessages.length} messages
              </span>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px' }}>
              {threadMessages.map((msg, i) => {
                const isHandler = msg.from === 'HANDLER'
                const color = isHandler ? 'var(--accent)' : getAgentColor(msg.from)
                return (
                  <div key={i} style={{
                    display: 'flex', flexDirection: 'column',
                    alignItems: isHandler ? 'flex-end' : 'flex-start',
                    marginBottom: 8,
                  }}>
                    <span style={{
                      color, fontFamily: 'var(--font-mono)', fontSize: 10, marginBottom: 2,
                    }}>
                      {msg.from}
                    </span>
                    <div style={{
                      background: isHandler ? 'rgba(129,140,248,0.12)' : 'rgba(167,139,250,0.08)',
                      border: '1px solid var(--border)', borderRadius: 6,
                      padding: '6px 10px', maxWidth: '70%', fontSize: 12,
                      color: 'var(--text-primary)', fontFamily: 'var(--font-mono)',
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    }}>
                      {msg.content}
                    </div>
                    <span style={{
                      color: 'var(--text-secondary)', fontSize: 9,
                      fontFamily: 'var(--font-mono)', marginTop: 2,
                    }}>
                      t={msg.t}
                    </span>
                  </div>
                )
              })}
              <div ref={messagesEndRef} />
            </div>

            {/* Reply input */}
            <div style={{
              padding: '12px 20px', borderTop: '1px solid var(--border)',
              display: 'flex', gap: 8,
            }}>
              <input
                type="text"
                value={reply}
                onChange={e => setReply(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
                placeholder={`Reply to ${selectedHandle}...`}
                style={{
                  flex: 1, background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border)', borderRadius: 4,
                  padding: '6px 10px', color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)', fontSize: 12,
                  outline: 'none',
                }}
              />
              <button
                onClick={handleSend}
                disabled={!reply.trim() || sending}
                style={{
                  background: reply.trim() ? 'var(--bg-surface)' : 'transparent',
                  border: `1px solid ${reply.trim() ? 'var(--accent)' : 'var(--border)'}`,
                  borderRadius: 4, padding: '6px 12px',
                  color: reply.trim() ? 'var(--accent)' : 'var(--text-secondary)',
                  cursor: reply.trim() ? 'pointer' : 'default',
                  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
                  whiteSpace: 'nowrap',
                }}
              >
                {sending ? '...' : 'SEND'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

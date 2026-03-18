import { useSimulation } from '../../api/hooks'
import type { Agent } from '../../api/types'

const ROLE_COLORS: Record<string, string> = {
  flour_forager: '#c8a',
  water_forager: '#48c',
  baker: '#ca4',
}

export function EconomyOverview() {
  const { agents, economy } = useSimulation()

  const totalFlour = agents.reduce((sum, a) => sum + (a.flour ?? 0), 0)
  const totalWater = agents.reduce((sum, a) => sum + (a.water ?? 0), 0)
  const totalBread = agents.reduce((sum, a) => sum + (a.bread ?? 0), 0)
  const totalCoins = agents.reduce((sum, a) => sum + (a.energy ?? 0), 0)

  const bakeCount = economy.counts.bake ?? 0
  const breadBaked = economy.counts.bread_baked ?? 0
  const tradeCount = economy.counts.give ?? 0
  const tradeVolume = economy.trade_volume

  // Per-role averages
  const roles = ['flour_forager', 'water_forager', 'baker'] as const
  const roleStats = roles.map(role => {
    const roleAgents = agents.filter(a => a.role === role)
    const count = roleAgents.length
    if (count === 0) return { role, count: 0, avgHunger: 0, avgThirst: 0, avgCoins: 0, avgFlour: 0, avgWater: 0, avgBread: 0 }
    return {
      role,
      count,
      avgHunger: roleAgents.reduce((s, a) => s + (a.hunger ?? 0), 0) / count,
      avgThirst: roleAgents.reduce((s, a) => s + (a.thirst ?? 0), 0) / count,
      avgCoins: roleAgents.reduce((s, a) => s + (a.energy ?? 0), 0) / count,
      avgFlour: roleAgents.reduce((s, a) => s + (a.flour ?? 0), 0) / count,
      avgWater: roleAgents.reduce((s, a) => s + (a.water ?? 0), 0) / count,
      avgBread: roleAgents.reduce((s, a) => s + (a.bread ?? 0), 0) / count,
    }
  })

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: 24 }}>
      <div style={{
        fontSize: 16, fontWeight: 700, color: 'var(--accent)',
        fontFamily: 'var(--font-mono)', marginBottom: 20, letterSpacing: 1,
      }}>
        ECONOMY OVERVIEW
      </div>

      {/* System totals */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24,
      }}>
        <StatCard label="Total Flour" value={totalFlour} color="#c8a" />
        <StatCard label="Total Water" value={totalWater} color="#48c" />
        <StatCard label="Total Bread" value={totalBread} color="#ca4" />
        <StatCard label="Total Coins" value={totalCoins} color="var(--text-primary)" />
      </div>

      {/* Activity */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24,
      }}>
        <StatCard label="Bakes" value={bakeCount} color="#34d399" />
        <StatCard label="Bread Baked" value={breadBaked} color="#34d399" />
        <StatCard label="Trades" value={tradeCount} color="#fb923c" />
      </div>

      {/* Trade volume */}
      {Object.keys(tradeVolume).length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <SectionLabel>Trade Volume (total units exchanged)</SectionLabel>
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 4, padding: 12, display: 'flex', gap: 20,
            fontSize: 13, fontFamily: 'var(--font-mono)',
          }}>
            {tradeVolume.flour != null && <span><span style={{ color: '#c8a' }}>{tradeVolume.flour}</span> flour</span>}
            {tradeVolume.water != null && <span><span style={{ color: '#48c' }}>{tradeVolume.water}</span> water</span>}
            {tradeVolume.bread != null && <span><span style={{ color: '#ca4' }}>{tradeVolume.bread}</span> bread</span>}
            {tradeVolume.coins != null && <span><span style={{ color: 'var(--text-primary)' }}>{tradeVolume.coins}</span> coins</span>}
          </div>
        </div>
      )}

      {/* Disparity charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div>
          <SectionLabel>Bread Distribution</SectionLabel>
          <DisparityChart agents={agents} metric="bread" color="#ca4" />
        </div>
        <div>
          <SectionLabel>Coin Distribution</SectionLabel>
          <DisparityChart agents={agents} metric="coins" color="var(--text-primary)" />
        </div>
        <div>
          <SectionLabel>Hunger Distribution</SectionLabel>
          <DisparityChart agents={agents} metric="hunger" color="#f59e0b" />
        </div>
        <div>
          <SectionLabel>Thirst Distribution</SectionLabel>
          <DisparityChart agents={agents} metric="thirst" color="#38bdf8" />
        </div>
      </div>

      {/* Per-role averages */}
      <SectionLabel>Per-Role Averages</SectionLabel>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 4, overflow: 'hidden',
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Role', 'Count', 'Hunger', 'Thirst', 'Coins', 'Flour', 'Water', 'Bread'].map(h => (
                <th key={h} style={{
                  padding: '8px 10px', textAlign: 'left',
                  color: 'var(--text-secondary)', fontWeight: 600, fontSize: 11,
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {roleStats.map(rs => (
              <tr key={rs.role} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '8px 10px', color: 'var(--text-primary)' }}>{rs.role}</td>
                <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }}>{rs.count}</td>
                <td style={{ padding: '8px 10px', color: rs.avgHunger > 60 ? '#f87171' : 'var(--text-primary)' }}>{rs.avgHunger.toFixed(0)}</td>
                <td style={{ padding: '8px 10px', color: rs.avgThirst > 60 ? '#f87171' : 'var(--text-primary)' }}>{rs.avgThirst.toFixed(0)}</td>
                <td style={{ padding: '8px 10px', color: 'var(--text-primary)' }}>{rs.avgCoins.toFixed(0)}</td>
                <td style={{ padding: '8px 10px', color: '#c8a' }}>{rs.avgFlour.toFixed(1)}</td>
                <td style={{ padding: '8px 10px', color: '#48c' }}>{rs.avgWater.toFixed(1)}</td>
                <td style={{ padding: '8px 10px', color: '#ca4' }}>{rs.avgBread.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 4, padding: '12px 14px',
    }}>
      <div style={{ color: 'var(--text-secondary)', fontSize: 11, fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color, fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
        {value}
      </div>
    </div>
  )
}

function DisparityChart({ agents, metric, color: _color }: { agents: Agent[]; metric: string; color: string }) {
  const getValue = (a: Agent) => {
    if (metric === 'coins') return a.energy ?? 0
    return (a as any)[metric] ?? 0
  }
  const sorted = [...agents].sort((a, b) => getValue(b) - getValue(a))
  const max = Math.max(1, ...sorted.map(getValue))

  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 4, padding: 10, maxHeight: 300, overflowY: 'auto',
    }}>
      {sorted.map(a => {
        const val = getValue(a)
        const pct = (val / max) * 100
        const roleColor = ROLE_COLORS[a.role ?? ''] ?? '#888'
        return (
          <div key={a.handle} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <span style={{
              width: 32, fontSize: 10, fontFamily: 'var(--font-mono)',
              color: roleColor, flexShrink: 0, textAlign: 'right',
            }}>
              {a.handle}
            </span>
            <div style={{ flex: 1, height: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
              <div style={{
                height: '100%', borderRadius: 2, width: `${pct}%`,
                background: roleColor, opacity: 0.8,
                transition: 'width 300ms ease',
              }} />
            </div>
            <span style={{ width: 28, fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', textAlign: 'right' }}>
              {val}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      color: 'var(--energy-healthy)', fontSize: 11, fontWeight: 600,
      textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6,
    }}>
      {children}
    </div>
  )
}

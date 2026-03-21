import { useState } from 'react'
import { useSimulation } from '../../api/hooks'
import type { Agent } from '../../api/types'

const ROLE_COLORS: Record<string, string> = {
  flour_forager: '#c8a',
  water_forager: '#48c',
  baker: '#ca4',
}

const TABS = [
  { key: 'coins', label: 'Coins', color: 'var(--text-primary)', getValue: (a: Agent) => a.energy ?? 0 },
  { key: 'flour', label: 'Flour', color: '#c8a', getValue: (a: Agent) => a.flour ?? 0 },
  { key: 'water', label: 'Water', color: '#48c', getValue: (a: Agent) => a.water ?? 0 },
  { key: 'bread', label: 'Bread', color: '#ca4', getValue: (a: Agent) => a.bread ?? 0 },
  { key: 'hunger', label: 'Hunger', color: '#f59e0b', getValue: (a: Agent) => a.hunger ?? 0 },
  { key: 'thirst', label: 'Thirst', color: '#38bdf8', getValue: (a: Agent) => a.thirst ?? 0 },
] as const

export function EconomyOverview() {
  const { agents, economy } = useSimulation()
  const [activeTab, setActiveTab] = useState('coins')

  const tab = TABS.find(t => t.key === activeTab) ?? TABS[0]

  const totalFlour = agents.reduce((sum, a) => sum + (a.flour ?? 0), 0)
  const totalWater = agents.reduce((sum, a) => sum + (a.water ?? 0), 0)
  const totalBread = agents.reduce((sum, a) => sum + (a.bread ?? 0), 0)
  const totalCoins = agents.reduce((sum, a) => sum + (a.energy ?? 0), 0)

  const bakeCount = economy.counts.bake ?? 0
  const tradeCount = (economy.counts.give ?? 0) + (economy.counts.trade ?? 0)
  const offerCount = economy.counts.offer ?? 0
  const forageCount = economy.counts.forage ?? 0
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

  // Distribution data
  const sorted = [...agents].sort((a, b) => tab.getValue(b) - tab.getValue(a))
  const max = Math.max(1, ...sorted.map(tab.getValue))
  const total = sorted.reduce((s, a) => s + tab.getValue(a), 0)
  const avg = agents.length ? total / agents.length : 0

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
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24,
      }}>
        <StatCard label="Forages" value={forageCount} color="#34d399" />
        <StatCard label="Bakes" value={bakeCount} color="#34d399" />
        <StatCard label="Offers" value={offerCount} color="#fb923c" />
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

      {/* Tabbed distribution */}
      <SectionLabel>Resource Distribution</SectionLabel>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 4, overflow: 'hidden', marginBottom: 24,
      }}>
        {/* Tab bar */}
        <div style={{
          display: 'flex', borderBottom: '1px solid var(--border)',
        }}>
          {TABS.map(t => (
            <div
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              style={{
                flex: 1, padding: '8px 0', textAlign: 'center', cursor: 'pointer',
                fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 600,
                color: activeTab === t.key ? t.color : 'var(--text-secondary)',
                borderBottom: activeTab === t.key ? `2px solid ${t.color}` : '2px solid transparent',
                background: activeTab === t.key ? 'rgba(255,255,255,0.03)' : 'transparent',
              }}
            >
              {t.label}
            </div>
          ))}
        </div>

        {/* Summary line */}
        <div style={{
          padding: '8px 12px', borderBottom: '1px solid var(--border)',
          fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)',
          display: 'flex', gap: 16,
        }}>
          <span>total: <span style={{ color: tab.color }}>{Math.round(total)}</span></span>
          <span>avg: <span style={{ color: tab.color }}>{avg.toFixed(1)}</span></span>
          <span>min: <span style={{ color: tab.color }}>{sorted.length ? Math.round(tab.getValue(sorted[sorted.length - 1])) : 0}</span></span>
          <span>max: <span style={{ color: tab.color }}>{sorted.length ? Math.round(tab.getValue(sorted[0])) : 0}</span></span>
        </div>

        {/* Bar chart */}
        <div style={{ padding: 10, maxHeight: 400, overflowY: 'auto' }}>
          {sorted.map(a => {
            const val = tab.getValue(a)
            const pct = (val / max) * 100
            const roleColor = ROLE_COLORS[a.role ?? ''] ?? '#888'
            return (
              <div key={a.handle} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                <span style={{
                  width: 36, fontSize: 10, fontFamily: 'var(--font-mono)',
                  color: roleColor, flexShrink: 0, textAlign: 'right',
                }}>
                  {a.handle}
                </span>
                <div style={{ flex: 1, height: 10, background: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
                  <div style={{
                    height: '100%', borderRadius: 2, width: `${pct}%`,
                    background: roleColor, opacity: 0.8,
                    transition: 'width 300ms ease',
                  }} />
                </div>
                <span style={{ width: 36, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {Math.round(val)}
                </span>
              </div>
            )
          })}
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
                <td style={{ padding: '8px 10px', color: ROLE_COLORS[rs.role] ?? 'var(--text-primary)' }}>{rs.role}</td>
                <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }}>{rs.count}</td>
                <td style={{ padding: '8px 10px', color: rs.avgHunger < 50 ? '#f87171' : 'var(--text-primary)' }}>{rs.avgHunger.toFixed(0)}</td>
                <td style={{ padding: '8px 10px', color: rs.avgThirst < 50 ? '#f87171' : 'var(--text-primary)' }}>{rs.avgThirst.toFixed(0)}</td>
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

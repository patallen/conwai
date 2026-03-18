import { useUIState } from '../../api/hooks'
import { SocialGraph } from '../graph/SocialGraph'
import { AgentDetail } from '../agents/AgentDetail'
import { ConversationView } from '../feed/ConversationView'
import { EconomyOverview } from '../economy/EconomyOverview'
import { BoardView } from '../feed/BoardView'

export function MainView() {
  const { view } = useUIState()

  return (
    <div style={{ height: '100%', overflow: 'hidden', minWidth: 0, position: 'relative' }}>
      {/* Graph is always mounted with absolute positioning — canvas handles its own sizing */}
      <div style={{
        position: 'absolute', inset: 0, overflow: 'hidden',
        visibility: view === 'graph' ? 'visible' : 'hidden',
        pointerEvents: view === 'graph' ? 'auto' : 'none',
      }}>
        <SocialGraph />
      </div>
      {/* Agent/conversation views are normal flow — they inherit the grid cell width */}
      {view === 'agent' && <AgentDetail />}
      {view === 'conversation' && <ConversationView />}
      {view === 'economy' && <EconomyOverview />}
      {view === 'board' && <BoardView />}
    </div>
  )
}

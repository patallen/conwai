export interface Agent {
  handle: string
  personality: string
  soul: string
  memory: string
  energy: number | null
  role: string | null
  flour: number
  water: number
  bread: number
  hunger: number | null
  thirst: number | null
  alive: boolean
  born_tick: number
}

export interface SimEvent {
  idx: number
  t: number
  entity: string
  type: string
  data: Record<string, any>
}

export interface BoardPost extends SimEvent {
  type: 'board_post'
  data: { content: string }
}

export interface AgentStats {
  handle: string
  events: number
  posts: number
  dms_sent: number
  dms_received: number
  remembers: number
  sleeping: number
  personality?: string
  soul?: string
}

export type HandlerAction =
  | { action: 'post_board'; content: string }
  | { action: 'send_dm'; to: string; content: string }
  | { action: 'set_energy'; handle: string; value: number }
  | { action: 'drain_energy'; handle: string; amount: number }
  | { action: 'drop_secret'; handle: string; content: string }

export interface ActionResult {
  ok: boolean
  error?: string
}

export interface SimulationData {
  agents: Agent[]
  events: SimEvent[]
  board: BoardPost[]
  conversations: Record<string, SimEvent[]>
  stats: AgentStats[]
  tick: number
  aliveCount: number
  totalEvents: number
}

export interface UIState {
  selectedAgent: string | null
  selectedConversation: string | null
  view: 'graph' | 'agent' | 'conversation' | 'economy' | 'board'
  controlPanelOpen: boolean
  controlPanelPrefill: Partial<HandlerAction> | null
}

export interface DataSource {
  subscribe(callback: (data: SimulationData) => void): void
  unsubscribe(): void
  getData(): SimulationData
  sendAction(action: HandlerAction): Promise<ActionResult>
}

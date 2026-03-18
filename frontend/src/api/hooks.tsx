import { createContext, useContext, useReducer, useEffect, useState, useCallback, type ReactNode, type Dispatch } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import type { SimulationData, UIState, DataSource, HandlerAction, ActionResult } from './types'

const SimulationContext = createContext<SimulationData | null>(null)
const SendActionContext = createContext<((action: HandlerAction) => Promise<ActionResult>) | null>(null)

export function SimulationProvider({ dataSource, children }: { dataSource: DataSource; children: ReactNode }) {
  const [data, setData] = useState<SimulationData>(dataSource.getData())
  useEffect(() => {
    dataSource.subscribe(setData)
    return () => dataSource.unsubscribe()
  }, [dataSource])
  const sendAction = useCallback((action: HandlerAction) => dataSource.sendAction(action), [dataSource])
  return (
    <SimulationContext.Provider value={data}>
      <SendActionContext.Provider value={sendAction}>{children}</SendActionContext.Provider>
    </SimulationContext.Provider>
  )
}

export function useSimulation(): SimulationData {
  const ctx = useContext(SimulationContext)
  if (!ctx) throw new Error('useSimulation must be used within SimulationProvider')
  return ctx
}

export function useSendAction(): (action: HandlerAction) => Promise<ActionResult> {
  const ctx = useContext(SendActionContext)
  if (!ctx) throw new Error('useSendAction must be used within SimulationProvider')
  return ctx
}

type UIAction =
  | { type: 'SELECT_AGENT'; handle: string }
  | { type: 'SELECT_CONVERSATION'; key: string }
  | { type: 'SHOW_GRAPH' }
  | { type: 'SHOW_ECONOMY' }
  | { type: 'SHOW_BOARD' }
  | { type: 'TOGGLE_CONTROL_PANEL' }
  | { type: 'OPEN_CONTROL_PANEL'; prefill?: Partial<HandlerAction> }
  | { type: 'CLOSE_CONTROL_PANEL' }

// Navigation dispatch that uses react-router + control panel state
export function useUIDispatch(): Dispatch<UIAction> {
  const navigate = useNavigate()
  const cpDispatch = useControlPanelDispatch()
  return useCallback((action: UIAction) => {
    switch (action.type) {
      case 'SELECT_AGENT': navigate(`/agent/${action.handle}`); break
      case 'SELECT_CONVERSATION': navigate(`/conversation/${action.key}`); break
      case 'SHOW_GRAPH': navigate('/'); break
      case 'SHOW_ECONOMY': navigate('/economy'); break
      case 'SHOW_BOARD': navigate('/board'); break
      case 'TOGGLE_CONTROL_PANEL':
      case 'OPEN_CONTROL_PANEL':
      case 'CLOSE_CONTROL_PANEL':
        cpDispatch(action)
        break
    }
  }, [navigate, cpDispatch])
}

// Derive UI state from current route
export function useUIState(): UIState {
  const location = useLocation()
  const path = location.pathname

  let view: UIState['view'] = 'graph'
  let selectedAgent: string | null = null
  let selectedConversation: string | null = null

  if (path.startsWith('/agent/')) {
    view = 'agent'
    selectedAgent = path.slice(7)
  } else if (path.startsWith('/conversation/')) {
    view = 'conversation'
    selectedConversation = path.slice(14)
  } else if (path === '/economy') {
    view = 'economy'
  } else if (path === '/board') {
    view = 'board'
  }

  const { controlPanelOpen, controlPanelPrefill } = useControlPanel()

  return { selectedAgent, selectedConversation, view, controlPanelOpen, controlPanelPrefill }
}

// Control panel state (not URL-driven)
type CPAction =
  | { type: 'TOGGLE_CONTROL_PANEL' }
  | { type: 'OPEN_CONTROL_PANEL'; prefill?: Partial<HandlerAction> }
  | { type: 'CLOSE_CONTROL_PANEL' }

interface CPState {
  controlPanelOpen: boolean
  controlPanelPrefill: Partial<HandlerAction> | null
}

function cpReducer(state: CPState, action: CPAction): CPState {
  switch (action.type) {
    case 'TOGGLE_CONTROL_PANEL': return { controlPanelOpen: !state.controlPanelOpen, controlPanelPrefill: null }
    case 'OPEN_CONTROL_PANEL': return { controlPanelOpen: true, controlPanelPrefill: action.prefill ?? null }
    case 'CLOSE_CONTROL_PANEL': return { controlPanelOpen: false, controlPanelPrefill: null }
    default: return state
  }
}

const CPStateContext = createContext<CPState>({ controlPanelOpen: false, controlPanelPrefill: null })
const CPDispatchContext = createContext<Dispatch<CPAction>>(() => {})

export function ControlPanelProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(cpReducer, { controlPanelOpen: false, controlPanelPrefill: null })
  return (
    <CPStateContext.Provider value={state}>
      <CPDispatchContext.Provider value={dispatch}>{children}</CPDispatchContext.Provider>
    </CPStateContext.Provider>
  )
}

export function useControlPanel(): CPState {
  return useContext(CPStateContext)
}

export function useControlPanelDispatch(): Dispatch<CPAction> {
  return useContext(CPDispatchContext)
}

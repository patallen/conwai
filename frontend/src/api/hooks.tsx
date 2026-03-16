import { createContext, useContext, useReducer, useEffect, useState, useCallback, type ReactNode, type Dispatch } from 'react'
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
  | { type: 'TOGGLE_CONTROL_PANEL' }
  | { type: 'OPEN_CONTROL_PANEL'; prefill?: Partial<HandlerAction> }
  | { type: 'CLOSE_CONTROL_PANEL' }

const initialUIState: UIState = {
  selectedAgent: null, selectedConversation: null, view: 'graph',
  controlPanelOpen: false, controlPanelPrefill: null,
}

function uiReducer(state: UIState, action: UIAction): UIState {
  switch (action.type) {
    case 'SELECT_AGENT': return { ...state, selectedAgent: action.handle, selectedConversation: null, view: 'agent' }
    case 'SELECT_CONVERSATION': return { ...state, selectedConversation: action.key, selectedAgent: null, view: 'conversation' }
    case 'SHOW_GRAPH': return { ...state, selectedAgent: null, selectedConversation: null, view: 'graph' }
    case 'TOGGLE_CONTROL_PANEL': return { ...state, controlPanelOpen: !state.controlPanelOpen, controlPanelPrefill: null }
    case 'OPEN_CONTROL_PANEL': return { ...state, controlPanelOpen: true, controlPanelPrefill: action.prefill ?? null }
    case 'CLOSE_CONTROL_PANEL': return { ...state, controlPanelOpen: false, controlPanelPrefill: null }
    default: return state
  }
}

const UIStateContext = createContext<UIState | null>(null)
const UIDispatchContext = createContext<Dispatch<UIAction> | null>(null)

export function UIProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(uiReducer, initialUIState)
  return (
    <UIStateContext.Provider value={state}>
      <UIDispatchContext.Provider value={dispatch}>{children}</UIDispatchContext.Provider>
    </UIStateContext.Provider>
  )
}

export function useUIState(): UIState {
  const ctx = useContext(UIStateContext)
  if (!ctx) throw new Error('useUIState must be used within UIProvider')
  return ctx
}

export function useUIDispatch(): Dispatch<UIAction> {
  const ctx = useContext(UIDispatchContext)
  if (!ctx) throw new Error('useUIDispatch must be used within UIProvider')
  return ctx
}

import { useMemo, useCallback, useRef, useEffect, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods, type NodeObject, type LinkObject } from 'react-force-graph-2d'
import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'
import type { Agent } from '../../api/types'

const RECENCY_WINDOW_S = 10
const EDGE_FADE_S = 60
const EDGE_MIN_OPACITY = 0.3

// graphData nodes only carry topology + stable properties (id, color).
// Volatile properties (energy, agent data) live in refs read at paint time.
interface GraphNodeData {
  id: string
  color: string
}

interface GraphLinkData {
  source: string
  target: string
}

type GNode = NodeObject<GraphNodeData>
type GLink = LinkObject<GraphNodeData, GraphLinkData>

export function SocialGraph() {
  const { agents, conversations, events } = useSimulation()
  const { selectedAgent } = useUIState()
  const dispatch = useUIDispatch()
  const graphRef = useRef<ForceGraphMethods<NodeObject<GraphNodeData>, LinkObject<GraphNodeData, GraphLinkData>>>(undefined)
  const containerRef = useRef<HTMLDivElement>(null)

  // --- Refs for volatile data (read at paint time, never in graphData) ---
  const agentsRef = useRef<Map<string, Agent>>(new Map())
  agentsRef.current = new Map(agents.map(a => [a.handle, a]))

  const conversationsRef = useRef(conversations)
  conversationsRef.current = conversations

  // Pre-compute recently active agents once per poll, not per frame
  const recentlyActiveRef = useRef<Set<string>>(new Set())
  recentlyActiveRef.current = useMemo(() => {
    const now = Date.now() / 1000
    const active = new Set<string>()
    for (const e of events) {
      if (e.entity && (now - e.t) < RECENCY_WINDOW_S) {
        active.add(e.entity)
      }
    }
    return active
  }, [events])

  const maxEnergyRef = useRef(1)
  maxEnergyRef.current = agents.reduce((max, a) => Math.max(max, a.energy ?? 0), 1)

  // --- Dead agent fade-out ---
  const prevAgentsRef = useRef<Set<string>>(new Set())
  const [fadingAgents, setFadingAgents] = useState<Map<string, { agent: Agent; fadeStart: number }>>(new Map())

  useEffect(() => {
    const currentHandles = new Set(agents.map(a => a.handle))
    const prev = prevAgentsRef.current

    for (const handle of prev) {
      if (!currentHandles.has(handle) && !fadingAgents.has(handle)) {
        setFadingAgents(m => {
          const next = new Map(m)
          next.set(handle, {
            agent: { handle, personality: '', soul: '', memory: '', energy: 0, alive: false, role: null, flour: 0, water: 0, bread: 0, hunger: null, thirst: null, born_tick: 0 } as Agent,
            fadeStart: Date.now(),
          })
          return next
        })
      }
    }

    for (const handle of currentHandles) {
      if (fadingAgents.has(handle)) {
        setFadingAgents(m => { const next = new Map(m); next.delete(handle); return next })
      }
    }

    prevAgentsRef.current = currentHandles
  }, [agents])

  useEffect(() => {
    if (fadingAgents.size === 0) return
    const timer = setInterval(() => {
      setFadingAgents(m => {
        const next = new Map(m)
        for (const [handle, { fadeStart }] of next) {
          if (Date.now() - fadeStart > 3000) next.delete(handle)
        }
        return next.size !== m.size ? next : m
      })
    }, 500)
    return () => clearInterval(timer)
  }, [fadingAgents.size])

  // --- Graph data: nodes + all possible link pairs. Never changes after initial population. ---
  // paintLink decides which edges to actually draw based on conversationsRef.
  const agentKeys = agents.map(a => a.handle).sort().join(',')
  const fadingKeys = Array.from(fadingAgents.keys()).sort().join(',')
  const convoKeys = Object.keys(conversations).sort().join(',')

  const graphData = useMemo(() => {
    const handleSet = new Set(agents.map(a => a.handle))
    const allHandles = [...handleSet, ...Array.from(fadingAgents.keys()).filter(h => !handleSet.has(h))]

    const nodes: GNode[] = allHandles.map(handle => ({
      id: handle,
      color: getAgentColor(handle),
    }))

    // Only create links for pairs where both agents exist as nodes
    const links: GLink[] = []
    for (const key of Object.keys(conversations)) {
      const [a, b] = key.split('-')
      if (a && b && handleSet.has(a) && handleSet.has(b)) {
        links.push({ source: a, target: b })
      }
    }

    return { nodes, links }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentKeys, fadingKeys, convoKeys])

  // Configure forces when graph data first populates
  const forcesConfigured = useRef(false)
  useEffect(() => {
    if (!graphRef.current || graphData.nodes.length === 0) return
    const fg = graphRef.current
    fg.d3Force('charge')?.strength(-400)
    fg.d3Force('center', null)
    // Link force with dynamic strength based on conversation weight
    const convosRef = conversationsRef
    fg.d3Force('link')
      ?.distance(100)
      .strength((link: any) => {
        const srcId = typeof link.source === 'object' ? link.source.id : link.source
        const tgtId = typeof link.target === 'object' ? link.target.id : link.target
        const key = [srcId, tgtId].sort().join('-')
        const msgs = convosRef.current[key]
        if (!msgs || msgs.length === 0) return 0 // no conversation = no attraction
        return Math.min(msgs.length * 0.005, 0.1) // gentle, scales with message count
      })
    if (!forcesConfigured.current) {
      forcesConfigured.current = true
      fg.d3ReheatSimulation()
    }
  }, [graphData])

  // --- Interactions ---
  const handleNodeClick = useCallback((node: GNode) => {
    dispatch({ type: 'SELECT_AGENT', handle: node.id! as string })
  }, [dispatch])

  const handleLinkClick = useCallback((link: GLink) => {
    const src = typeof link.source === 'object' ? (link.source as GNode).id : link.source
    const tgt = typeof link.target === 'object' ? (link.target as GNode).id : link.target
    const key = [src, tgt].sort().join('-')
    dispatch({ type: 'SELECT_CONVERSATION', key })
  }, [dispatch])

  const nodeLabel = useCallback((node: GNode) => {
    const a = agentsRef.current.get(node.id as string)
    if (!a) return node.id as string
    return `${a.handle}\n${a.personality}\nenergy: ${a.energy ?? '?'}\n${a.soul ? a.soul.slice(0, 80) : ''}`
  }, [])

  // --- Paint callbacks: read volatile data from refs ---
  const selectedAgentRef = useRef(selectedAgent)
  selectedAgentRef.current = selectedAgent

  const fadingAgentsRef = useRef(fadingAgents)
  fadingAgentsRef.current = fadingAgents

  const paintNode = useCallback((node: GNode, ctx: CanvasRenderingContext2D) => {
    const agent = agentsRef.current.get(node.id as string)
    const energy = agent?.energy ?? 0
    const maxEnergy = maxEnergyRef.current
    const radius = 5 + (energy / maxEnergy) * 10
    const isSelected = selectedAgentRef.current === node.id

    // Fade out dying agents
    const fadeEntry = fadingAgentsRef.current.get(node.id as string)
    if (fadeEntry) {
      const elapsed = Date.now() - fadeEntry.fadeStart
      ctx.globalAlpha = Math.max(0, 1 - elapsed / 3000)
    }

    const recentlyActive = recentlyActiveRef.current.has(node.id as string)

    // Glow effect for active nodes
    if (recentlyActive) {
      ctx.beginPath()
      ctx.arc(node.x!, node.y!, radius + 4, 0, Math.PI * 2)
      ctx.fillStyle = node.color + '30'
      ctx.fill()
    }

    // Node circle
    ctx.beginPath()
    ctx.arc(node.x!, node.y!, radius, 0, Math.PI * 2)
    ctx.fillStyle = node.color + '20'
    ctx.fill()
    ctx.strokeStyle = isSelected ? '#e2e8f0' : node.color
    ctx.lineWidth = isSelected ? 2 : 1.5
    ctx.stroke()

    // Label
    ctx.font = '4px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = node.color
    ctx.fillText(node.id as string, node.x!, node.y! + radius + 3)

    ctx.globalAlpha = 1
  }, []) // stable — reads everything from refs

  const paintLink = useCallback((link: GLink, ctx: CanvasRenderingContext2D) => {
    const src = link.source as GNode
    const tgt = link.target as GNode
    if (!src.x || !tgt.x) return

    // Look up current conversation data from ref
    const srcId = src.id as string
    const tgtId = tgt.id as string
    const key = [srcId, tgtId].sort().join('-')
    const msgs = conversationsRef.current[key]

    // No conversation between these agents — don't draw
    if (!msgs || msgs.length === 0) return

    const weight = msgs.length
    const lastActivity = msgs[msgs.length - 1]?.t ?? 0

    const age = Date.now() / 1000 - lastActivity
    const opacity = age > EDGE_FADE_S
      ? EDGE_MIN_OPACITY
      : EDGE_MIN_OPACITY + (1 - EDGE_MIN_OPACITY) * (1 - age / EDGE_FADE_S)

    ctx.beginPath()
    ctx.moveTo(src.x, src.y!)
    ctx.lineTo(tgt.x, tgt.y!)
    ctx.strokeStyle = `rgba(124, 58, 237, ${opacity})`
    ctx.lineWidth = Math.min(0.5 + weight * 0.3, 4)
    ctx.stroke()
  }, []) // stable — reads everything from refs

  return (
    <div
      ref={containerRef}
      style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse at center, #131520 0%, #0f1117 70%)',
        overflow: 'hidden',
      }}
    >
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        nodeCanvasObject={paintNode}
        nodeLabel={nodeLabel}
        linkCanvasObject={paintLink}
        linkDirectionalParticles={(link: GLink) => {
          const src = link.source as GNode
          const tgt = link.target as GNode
          const srcId = typeof src === 'string' ? src : src.id as string
          const tgtId = typeof tgt === 'string' ? tgt : tgt.id as string
          return (recentlyActiveRef.current.has(srcId) || recentlyActiveRef.current.has(tgtId)) ? 3 : 0
        }}
        linkDirectionalParticleSpeed={0.01}
        linkDirectionalParticleColor={() => 'rgba(167, 139, 250, 0.6)'}
        linkDirectionalParticleWidth={2}
        onNodeClick={handleNodeClick}
        onLinkClick={handleLinkClick}
        nodeId="id"
        enableZoomInteraction={true}
        enablePanInteraction={true}
        enableNodeDrag={true}
        cooldownTicks={Infinity}
        backgroundColor="transparent"
      />
    </div>
  )
}

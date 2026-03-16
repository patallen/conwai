import type { DataSource, SimulationData, HandlerAction, ActionResult, BoardPost } from './types'

const EMPTY_DATA: SimulationData = {
  agents: [], events: [], board: [], conversations: {},
  stats: [], tick: 0, aliveCount: 0, totalEvents: 0,
}

export class PollingTransport implements DataSource {
  private data: SimulationData = EMPTY_DATA
  private callbacks: Set<(data: SimulationData) => void> = new Set()
  private intervalId: ReturnType<typeof setInterval> | null = null
  private lastEventIdx = 0
  private pollIntervalMs: number

  constructor(pollIntervalMs = 1000) {
    this.pollIntervalMs = pollIntervalMs
  }

  subscribe(callback: (data: SimulationData) => void): void {
    this.callbacks.add(callback)
    if (this.callbacks.size === 1) this.start()
    callback(this.data)
  }

  unsubscribe(): void {
    this.callbacks.clear()
    this.stop()
  }

  getData(): SimulationData { return this.data }

  async sendAction(action: HandlerAction): Promise<ActionResult> {
    const resp = await fetch('/api/handler', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(action),
    })
    return resp.json()
  }

  private start(): void {
    this.poll()
    this.intervalId = setInterval(() => this.poll(), this.pollIntervalMs)
  }

  private stop(): void {
    if (this.intervalId) { clearInterval(this.intervalId); this.intervalId = null }
  }

  private async poll(): Promise<void> {
    try {
      const [agents, newEvents, board, conversations, stats, status] = await Promise.all([
        fetch('/api/agents').then(r => r.json()),
        fetch(`/api/events?since=${this.lastEventIdx}`).then(r => r.json()),
        fetch('/api/board').then(r => r.json()),
        fetch('/api/conversations').then(r => r.json()),
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/status').then(r => r.json()),
      ])

      let events = [...this.data.events, ...newEvents]
      if (events.length > 500) events = events.slice(events.length - 500)
      if (newEvents.length > 0) this.lastEventIdx = newEvents[newEvents.length - 1].idx + 1

      this.data = {
        agents, events, board: board as BoardPost[], conversations, stats,
        tick: status.tick ?? 0, aliveCount: status.alive ?? 0, totalEvents: status.total_events ?? 0,
      }

      for (const cb of this.callbacks) cb(this.data)
    } catch (err) {
      console.warn('Poll failed:', err)
    }
  }
}

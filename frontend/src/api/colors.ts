const PALETTE = [
  '#818cf8', '#f472b6', '#34d399', '#fb923c',
  '#a78bfa', '#38bdf8', '#facc15', '#f87171',
  '#2dd4bf', '#c084fc', '#4ade80', '#f97316',
  '#67e8f9', '#e879f9', '#a3e635', '#fbbf24',
]

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function getAgentColor(handle: string): string {
  return PALETTE[hashString(handle) % PALETTE.length]
}

# Cognitive Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                        BlackboardBrain                              │
│                    (processes run sequentially)                      │
│                                                                     │
│  ┌──────────────┐                                                   │
│  │  Perception   │ tick, resources, board posts, DMs, action results │
│  └──────┬───────┘                                                   │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────┐                                               │
│  │ Strategic Review  │ every 24 ticks                                │
│  │                   │ reads: diary, strategy, inventory             │
│  │  [LLM call → 122B]│ writes: memory.strategy                      │
│  └──────┬────────────┘                                              │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────┐                                           │
│  │ Memory Compression    │ every tick                                │
│  │                       │ collapses last tick's messages → diary    │
│  │  [embeds new entries] │ archives old entries with embeddings      │
│  └──────┬────────────────┘                                          │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────┐                                           │
│  │ Consolidation         │ every 24 ticks                           │
│  │                       │                                          │
│  │  1. Recent diary ──────► Focal-point questions [LLM → 27B]      │
│  │                       │                                          │
│  │  2. Questions ─────────► Embed → retrieve diary evidence         │
│  │                       │                                          │
│  │  3. Evidence ──────────► Generate insight [LLM → 27B]           │
│  │                       │                                          │
│  │  4. Insight ───────────► Store as [Reflection] diary entry       │
│  │                       │  with embedding (participates in recall) │
│  └──────┬────────────────┘                                          │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────┐                                           │
│  │ Memory Recall         │ every tick                                │
│  │                       │                                          │
│  │  embed(perception) ───► cosine similarity vs all diary entries   │
│  │                       │  reflections get 1.5× similarity boost   │
│  │                       │  top 5 → board["recalled"]               │
│  └──────┬────────────────┘                                          │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────┐                                           │
│  │ Context Assembly      │ every tick                                │
│  │                       │                                          │
│  │  builds LLM prompt:   │                                          │
│  │    1. Identity         │ (handle, personality, role, soul)       │
│  │    2. Recent messages  │ (tick summaries, context window)        │
│  │    3. Recalled memories│ (diary entries + reflections)           │
│  │    4. Current percept  │ (resources, board, DMs, feedback)      │
│  └──────┬────────────────┘                                          │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────┐                                           │
│  │ Inference             │ every tick                                │
│  │                       │                                          │
│  │  [LLM call → 122B]   │ system prompt + assembled messages       │
│  │                       │ → reasoning + tool calls                 │
│  │                       │ → decisions (forage, bake, trade, etc)   │
│  └──────┬────────────────┘                                          │
│         │                                                           │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          ▼
    ┌───────────┐
    │  Engine    │ executes decisions, updates world state
    │           │ results become next tick's action_feedback
    └───────────┘
```

## Data Flow

```
diary entries ◄──── MemoryCompression (every tick)
      │
      ├──── embeddings (bge-large, CPU)
      │
      ├──── recalled by MemoryRecall (cosine similarity)
      │
      └──── read by Consolidation (every 24 ticks)
                  │
                  ├──── focal-point questions (27B LLM)
                  │
                  ├──── evidence retrieval (embedding similarity)
                  │
                  └──── insights → stored back as diary entries
                              │
                              └──── [Reflection] prefix
                                    1.5× recall boost
                                    participates in future reflections
```

## Two LLM Endpoints

```
122B (H200s)                    27B (3090s)
├── Strategic Review            ├── Focal-point questions
├── Main Inference              └── Insight generation
└── (every tick per agent)          (every 24 ticks per agent)
```

## Memory Hierarchy

```
Working Memory          │ current tick's messages, perception
  (context window)      │ trimmed when too large
                        │
Short-term Memory       │ recent tick summaries (last 16)
  (messages list)       │ compressed by MemoryCompression
                        │
Long-term Memory        │ diary entries with embeddings
  (diary)               │ recalled by similarity
                        │
Semantic Memory         │ [Reflection] entries
  (consolidation)       │ generated from diary patterns
                        │ 1.5× recall priority
                        │
Identity                │ personality, role, soul, strategy
  (components)          │ updated by agent or strategic review
```

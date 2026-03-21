# Experiment 0020: Sentence Decomposition

## Results
- 587 sentences from 251 entries (avg 2.3 per entry)
- Sentence-level mean sim: **0.6036** (vs 0.7972 for entries)
- K=15 produces very distinct sentence clusters

### Sentence cluster highlights
| Cluster | Sentences | Pattern |
|---------|-----------|---------|
| 0 | 23 | "I will decline..." — trade rejections |
| 1 | 33 | "I am critically..." — crisis state |
| 2 | 32 | "I am skeptical of..." — evaluations |
| 5 | 39 | "Let me..." — action decisions |
| 7 | 85 | Action declarations (forage/bake/trade) |
| 11 | 44 | "Given my skeptical nature..." — personality reasoning |
| 12 | 10 | "No haggling" — specific recurring phrase |
| 14 | 18 | "I will ignore..." — dismissals |

## Analysis
Individual sentences are much more distinctive than full entries because each sentence focuses on ONE thing — a state description, a decision, a justification. Full entries blend 2-3 of these together, creating overlap.

The sentence clusters are genuinely behavioral — "I will decline" sentences group together regardless of what was being declined. Same for "I am skeptical of" — the skepticism pattern emerges at the sentence level.

## Key insight
Sentence-level decomposition + embedding works for pattern detection. The challenge: mapping sentence clusters back to entry-level concepts for consolidation. An entry might have sentences in different clusters — it's a multi-label problem.

## New ideas
- Tag each entry with which sentence clusters it participates in (feature vector)
- Use sentence cluster membership as the entry representation
- Focus on ACTION sentences (decisions) rather than all sentences

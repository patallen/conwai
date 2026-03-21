# Experiment 0005: Direct LLM Categorization

## Hypothesis
Skip embeddings entirely. Have the LLM discover patterns from a sample, then classify all entries into those patterns.

## Method
- Phase 1: Send 90 sample entries to LLM, ask for 8-12 behavioral patterns
- Phase 2: Send all entries in batches of 30, classify each into discovered patterns
- Total LLM calls: ~10 (1 discovery + 9 classification batches)

## Results
**10 patterns discovered, all 251 entries classified (100%).**

| # | Pattern | Count | Action Types |
|---|---------|-------|-------------|
| 1 | Skeptical verification before trade | 17 | forage, post, vote, offer, DM |
| 2 | Desperate abandonment of deliberate pacing | 55 | forage, DM, bake, accept |
| 3 | Strategic rejection of unfavorable rates | 56 | forage, accept, offer, bake |
| 4 | Rigid adherence to safety thresholds | 5 | bake, forage, post |
| 5 | Leveraging coin surplus for acquisition | 14 | offer, pay, DM |
| 6 | Raw material accumulation over finished goods | 6 | accept, offer, post |
| 7 | Immediate baking upon resource sufficiency | 25 | bake |
| 8 | Partner selection by complementary needs | 51 | inspect, offer, forage |
| 9 | Refusal to trade essential reserves | 3 | forage |
| 10 | Post-stability proactive replenishment | 19 | forage |

## Analysis
**Best result so far.** Compared to 0004 (LLM abstracts + embedding + clustering):
- Richer descriptions: full sentences explaining the pattern, not just 5-10 word labels
- Complete classification: every entry assigned (0004 had unclustered entries)
- Cross-cutting patterns: patterns span multiple action types (8/10 involve 2+ action types)
- 10x fewer LLM calls (10 vs 251)
- No embedding model needed (saves 1.2GB RAM + compute)

The patterns are genuinely actionable. An agent could use these as rules:
- "When starving, abandon deliberate pacing and take immediate action"
- "Reject trades below 1:1 rate unless survival is at stake"
- "Verify partner reliability before committing to trade"
- "Once stable, proactively forage to build surplus beyond minimums"

## Key Insight
**The embedding+clustering pipeline is unnecessary.** The LLM can discover AND classify patterns in one pass, with better results and far lower cost. The LLM understands behavioral intent natively — embedding models capture topic similarity, which is orthogonal to what we need.

## Implications for the system
- Consolidation pipeline: LLM discovers patterns from diary → LLM classifies new entries → patterns become first-class concepts
- Can run periodically (e.g., every 24-48 ticks) on recent diary entries
- Patterns can be injected into prompts as "lessons learned"
- Only need the local Qwen model, no embedding model for consolidation

## Remaining questions
- How stable are the patterns across different samples? (Run on different agents?)
- Do patterns evolve over time? (Run on first half vs second half of diary?)
- Can we merge/split patterns incrementally as new entries arrive?

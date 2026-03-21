# Experiment 0040: Outcome Tracking

## Results
Added outcome signals to the condition→decision→branch pipeline. Tracked crisis resolution rate and bread improvement for each branch.

### Key finding: Situation 3 ("critical risk, zero bread")
| Branch | Decision | Episodes | Crisis Resolved |
|--------|----------|----------|----------------|
| 1 | Bake immediately | 6 | **33%** |
| 2 | Forage (default) | 22 | 14% |
| 3 | Send DM / negotiate | 12 | 8% |

**Baking resolves crises 3x more often than foraging and 4x more than messaging.** But Helen defaults to foraging (22 eps) because of her "skeptical, self-reliant" personality.

### Situation 4 ("stable but water low")
| Branch | Decision | Episodes | Crisis Resolved |
|--------|----------|----------|----------------|
| 1 | Trade offers | 8 | 0% |
| 2 | Forage | 8 | **38%** |
| 3 | Bake surplus | 27 | 19% |

Foraging works best when water is the bottleneck.

## What this means for consolidation
The consolidated knowledge isn't just "in crisis → forage/bake/message." It's "in crisis → baking works best (33%) but I usually forage (14%)." This is ACTIONABLE — the agent can adjust its behavior based on empirical outcome data.

## The complete pipeline
1. Split entry into condition (first sentence) + decision (last sentence)
2. Embed both with residual+PCA
3. Cluster conditions → situation types
4. Within each situation, cluster decisions → behavioral branches
5. Track outcomes (next entry's state) per branch
6. Consolidated knowledge = situation + branches + outcome rates
7. The agent learns: "in situation X, strategy A works Y% of the time"

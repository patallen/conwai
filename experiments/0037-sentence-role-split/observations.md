# Experiment 0037: Condition+Decision Sentence Split

## Results
Split each entry into first sentence (condition/state) and last sentence (decision/action). Embed each separately with residual+PCA(3), concatenate, cluster the 6D pairs.

### Key patterns at K=10
| Pattern | Episodes | Condition | Decision |
|---------|----------|-----------|----------|
| 2 | 21 | Critically starving, zero bread | Immediately bake available flour |
| 4 | 28 | Critically starving, zero bread/flour | Forage immediately, don't trust offers |
| 8 | 28 | Zero bread, desperate | Spend coins on bread from specific agents |
| 5 | 30 | Reached targets but bread dropping | Keep foraging to maintain surplus buffer |
| 10 | 19 | See agents with complementary resources | Propose trade at fair rate |
| 7 | 25 | Skeptical of bad offer | Forage instead of accepting |
| 6 | 19 | Surplus but skeptical | DM/verify before committing |

## What works
- Condition+decision pairs produce genuine IF-THEN patterns
- Patterns 2 and 4 show two different responses to the same condition (bake vs forage when starving) — this is real behavioral variation that the agent could learn from
- No regex needed — just first/last sentence heuristic + embedding

## Comparison
| Approach | Silhouette | Pattern quality |
|----------|-----------|----------------|
| Raw embedding K=10 | 0.22 | Categories, not patterns |
| Residual+PCA K=10 | 0.52 | Better categories |
| Structured tuples (regex) | N/A | Right idea, brittle |
| Tuple embedding merge | 0.45 | Merged patterns, some noise |
| **Condition+Decision split** | 0.31 | **Genuine IF-THEN rules** |

Silhouette is lower but pattern quality is higher — the metric doesn't capture what matters.

## Key insight
Separating WHAT THE AGENT OBSERVED from WHAT IT DECIDED is the right decomposition for consolidation. The consolidated knowledge is the association between situation-type and action-type.

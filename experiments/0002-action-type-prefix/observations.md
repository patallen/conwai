# Experiment 0002: Action-Type Prefix

## Hypothesis
Prefixing the action type (forage, inspect, bake, etc.) to reasoning text before embedding would add discriminative signal.

## Results
| Threshold | Clusters | Sizes (top) |
|-----------|----------|-------------|
| 0.70      | 3        | 248, 2, 1   |
| 0.75      | 5        | 139, 80, 19, ... |
| 0.80      | 15       | 80, 40, 40, 33, 31, 3, ... |
| 0.85      | 26       | 37, 33, 28, 27, 26, 21, ... |

At 0.80, clusters roughly correspond to action types:
- Cluster 1 (80): mixed — still a mega-cluster of miscellaneous
- Cluster 2 (40): inspect entries
- Cluster 3 (40): forage (routine/stable)
- Cluster 4 (33): bake entries
- Cluster 5 (31): forage (desperate/starving)
- Cluster 6 (3): payment entries
- 9 singletons

## Analysis
The prefix helps — it separates by action type and even splits forage into routine vs desperate. But the clusters are action-type groupings, not behavioral patterns. The 80-entry mixed cluster still exists.

**Compared to 0004 (LLM abstracts):** 0004 produces more meaningful distinctions (reject risky trade, verify reliability, emergency spending) that cut ACROSS action types. Action-type prefix captures WHAT was done, LLM abstracts capture WHY.

## Verdict
Modest improvement over baseline, but far less useful than LLM abstraction. The action type is the only clear axis of variation for embeddings — once you add it, you've exhausted what the embedding model can offer.

# Experiment 0007: Batch LLM Abstracts

## Hypothesis
Sending 10 entries per LLM call produces comparable abstracts to individual calls, at 10x lower cost.

## Results

### Embedding Space
| Metric | Raw Reasoning | 0004 Individual | 0007 Batch |
|--------|--------------|-----------------|------------|
| Mean pairwise sim | 0.7972 | 0.6856 | **0.6330** |
| Std dev | 0.0745 | 0.0913 | 0.0962 |
| LLM calls | 0 | 251 | 26 |

Batch abstracts produce LOWER pairwise similarity than individual ones — entries are more spread out.

### Clustering
| Threshold | Clusters | Non-singleton |
|-----------|----------|---------------|
| 0.65      | 4        | 2             |
| 0.70      | 6        | 4             |
| 0.75      | 19       | 13            |
| 0.80      | 53       | 25            |

At 0.75: 19 clusters (13 non-singleton). Major groups: partner assessment (76), resource exchange (71), emergency foraging (35), strategic rejection (20), inspection (11), baking (11), public identity (6).

## Analysis
Batch mode works well:
- Better spread than individual abstracts (mean sim 0.63 vs 0.69)
- 10x fewer LLM calls (26 vs 251)
- Abstracts are comparable quality — slightly more varied because the LLM sees neighboring entries and differentiates more

The two largest clusters (76, 71) are still big but less dominant than 0004's mega-cluster (131 at 0.75).

## Verdict
If we keep the embedding+clustering approach, batch abstracts are strictly better than individual ones: cheaper AND better quality. But experiment 0005 (direct LLM categorization) may make this entire approach unnecessary.

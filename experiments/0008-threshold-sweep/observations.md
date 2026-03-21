# Experiment 0008: Threshold Sweep

## Hypothesis
Higher thresholds will reveal internal sub-structure within the mega-blob.

## Results

### Pairwise Similarity Distribution
| Stat     | Value  |
|----------|--------|
| Min      | 0.3336 |
| Max      | 1.0000 |
| Mean     | 0.7972 |
| Median   | 0.8044 |
| Std dev  | 0.0745 |
| 25th pct | 0.7598 |
| 75th pct | 0.8453 |
| 90th pct | 0.8829 |
| 95th pct | 0.9026 |

### Threshold Sweep (clique-based, max size 5)
| Threshold | Clusters | Unclustered |
|-----------|----------|-------------|
| 0.70      | 251      | 0           |
| 0.75      | 250      | 1           |
| 0.80      | 248      | 3           |
| 0.85      | 241      | 10          |
| 0.90      | 227      | 24          |
| 0.95      | 108      | 143         |

## Analysis
**The embedding space is a single dense ball.** Mean pairwise similarity is 0.80, std dev only 0.075. The bulk of entries sit between 0.73–0.87 cosine similarity. There is no bimodal or multimodal structure — just one tight cloud.

The clique-based clustering produces many overlapping clusters of size 5 at every threshold, because every local neighborhood is dense. Even at 0.95, there are 108 cliques. These aren't meaningful sub-groups — they're just overlapping patches on the surface of a uniform ball.

At 0.95, the clusters are "near-duplicate" entries (e.g., two inspect-Matthew entries from different ticks with slightly different numbers). This is deduplication, not concept extraction.

## Key Insight
**There is no sub-structure to find with higher thresholds.** The distribution is unimodal. Threshold tuning is a dead end for this data.

## Combined findings (with 0001 and 0009)
1. **0001**: Stripping vocabulary → still 1 blob. Problem is not vocabulary.
2. **0008**: Pairwise mean 0.80, unimodal. No sub-structure exists in embedding space.
3. **0009**: Last sentences → 206 clusters. Too specific.

**Conclusion: off-the-shelf sentence embeddings cannot separate these entries because they genuinely ARE about the same thing (agent reasoning about resource decisions). We need to change the REPRESENTATION, not tune the clustering.**

## Next direction
Need to embed at a different level of abstraction. Options:
- LLM-extracted behavioral abstracts (5-10 word pattern descriptions)
- Action-type categorization as a first-stage filter
- Two-stage: bucket by action type, then sub-cluster within

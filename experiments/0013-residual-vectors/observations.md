# Experiment 0013: Residual Vectors

## Hypothesis
Subtracting the corpus centroid removes the shared "resource management" component, leaving only what's distinctive about each entry.

## Results
| Metric | Original | Residual |
|--------|----------|----------|
| Mean sim | 0.7972 | -0.0030 |
| Std | 0.0745 | 0.2283 |

Std improved 3x. Centered around zero as expected.

### Clustering at threshold 0.10: 8 clusters (all non-singleton)
| Cluster | Size | Actions | Behavioral Pattern |
|---------|------|---------|-------------------|
| 1 | 60 | mixed (forage-heavy) | **Rejecting bad trades** — "decline", "ignore", "forbids" |
| 2 | 49 | inspect-heavy | **Assessment/inspection** — evaluating agents and opportunities |
| 3 | 45 | forage+bake | **Desperate survival** — "starving", "zero bread", "critical" |
| 4 | 31 | send_message+offer | **Urgent deal-making** — DMs, coin payments, pressure |
| 5 | 30 | bake+forage | **Stable production** — baking from position of strength |
| 6 | 20 | accept+offer | **Skeptical trade evaluation** — evaluating then accepting/rejecting |
| 7 | 10 | forage | **Post-trade maintenance** — water replenishment after deals |
| 8 | 6 | offer | **Transitional offers** — small surplus, trying to trade up |

## Analysis
**BEST EMBEDDING RESULT SO FAR.** Residual vectors produce meaningful behavioral clusters without any LLM. The patterns mix action types (cluster 1 has forage, bake, accept, send_message, offer — unified by the pattern of "rejecting unfavorable deals"). This is genuine behavioral clustering, not action-type grouping.

The key insight: the corpus centroid captures "average resource management reasoning." Subtracting it leaves the DEVIATION — what makes this specific entry different from average. These deviations cluster by behavioral intent.

## Comparison
| Approach | Mean Sim | Clusters at sweet spot | Behavioral? |
|----------|----------|----------------------|-------------|
| Raw embeddings (0.70) | 0.80 | 1 mega-blob | No |
| TF-IDF K=10 | 0.19 | 10 | Somewhat |
| Residual (0.10) | ~0 | 8 | **Yes** |
| Sentiment features K=10 | N/A | 10 | Yes |

## New ideas
- Combine residual vectors with K-means (0014 uses raw vectors — should re-run on residuals)
- Residual + PCA: project residuals to top PCs for even sharper clustering
- Residual + Hebbian: co-recall boosting on residuals might work since they're already spread

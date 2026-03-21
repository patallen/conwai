# Experiment 0030: Cross-Agent Residual+PCA

## Results
| Agent | 3 PCs K=5 sil | 3 PCs K=8 sil |
|-------|--------------|--------------|
| Jeffery | 0.46 | 0.44 |
| Adam | **0.72** | **0.63** |
| Cassandra | 0.68 | 0.54 |

All significantly above raw embedding baseline (~0.22).

## Key observations
- **Adam** has the cleanest clusters — his behavior is more differentiated (41 forage entries clearly split into "streak building", "flour replenishment", "water replenishment" sub-patterns)
- **Cassandra** has interesting clusters: "rejecting fair trades" cluster (12 entries) captures her rigid valuation enforcement
- **Jeffery** has lowest silhouette — his competitive nature makes him more varied/less predictable

## Analysis
**Residual+PCA generalizes across agents.** Different agents produce different cluster structures that reflect their personalities, but the technique works consistently. The 3-5 PCs sweet spot holds across all agents.

This validates the approach for production use.

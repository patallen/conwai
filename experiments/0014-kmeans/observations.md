# Experiment 0014: K-means Clustering

## Results
Best silhouette: residual K=8 at 0.2386.

| K | Raw Silhouette | Residual Silhouette |
|---|---------------|-------------------|
| 5 | 0.2216 | 0.2205 |
| 8 | 0.2284 | **0.2386** |
| 10 | 0.2168 | 0.2366 |
| 15 | 0.2070 | 0.2125 |

Residual vectors consistently better at K=8,10.

### Residual K=10 cluster highlights
- Cluster 0 (20): proactive foraging + public posts — building position
- Cluster 1 (30): urgent messaging — DMs, payments, pressure
- Cluster 4 (16): skeptical rejections — "forbids", "1:1 offer"
- Cluster 5 (41): desperate survival — "starving", "zero bread"
- Cluster 7 (28): stable baking — converting resources
- Cluster 8 (16): trade evaluation from stable position

## Key observation
K-means on residuals gives similar quality to threshold-based residual clustering (0013) but doesn't require choosing a threshold — just K. Silhouette scores are modest (~0.23) but the clusters are behaviorally meaningful.

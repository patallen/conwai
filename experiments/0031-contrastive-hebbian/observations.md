# Experiment 0031: Contrastive Hebbian on Residual+PCA

## Results
**Silhouette improved from 0.52 → 0.62** over 5 passes. Monotonic improvement each pass.

| Pass | Mean Sim | Std | Silhouette (K=8) |
|------|----------|-----|-----------------|
| 0 | 0.0009 | 0.474 | 0.524 |
| 1 | 0.0010 | 0.474 | 0.543 |
| 2 | 0.0011 | 0.475 | 0.556 |
| 3 | 0.0011 | 0.476 | 0.567 |
| 4 | 0.0012 | 0.476 | 0.575 |
| 5 | 0.0013 | 0.477 | **0.624** |

## Why it works (vs 0018 which failed)
1. Applied to residual+PCA space (already spread), not raw dense ball
2. Repulsion term pushes non-co-recalled entries apart (0018 had no repulsion)
3. Low-dimensional space (5D) means small updates have real impact

## Cluster quality (K=8)
| Cluster | Size | Actions | Pattern |
|---------|------|---------|---------|
| 0 | 40 | inspect | Assessment |
| 1 | 39 | forage+bake | Desperate survival |
| 2 | 10 | vote+post | Social/governance |
| 3 | 32 | bake+forage | Stable production |
| 4 | 41 | DM+offer | Urgent deal-making |
| 5 | 15 | forage | Proactive replenishment |
| 6 | 31 | forage | Trade rejection/skepticism |
| 7 | 43 | mixed | Trade evaluation |

## Key insight
Contrastive Hebbian on the right space (residual+PCA) is the best embedding-based approach: silhouette 0.62, genuine behavioral clusters, and it's an ONLINE algorithm — can run during gameplay as memories are co-recalled. This is the consolidation mechanism we've been looking for.

## The full pipeline
1. Embed diary entries (bge-large)
2. Subtract corpus centroid (residual)
3. Project to top 3-5 PCs
4. Co-recall reinforcement with repulsion (contrastive Hebbian)
5. K-means to extract clusters
6. Each cluster IS a consolidated concept

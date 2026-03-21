# Experiment 0029: Residual + PCA Combo

## Results
**Best silhouette of ANY experiment: 0.60 (residual + 3 PCs, K=5).**

| PCs | Best K | Silhouette |
|-----|--------|-----------|
| 2 | 5 | 0.540 |
| 3 | 5 | **0.601** |
| 5 | 5 | 0.546 |
| 5 | 10 | 0.524 |
| 10 | 5 | 0.415 |
| 20 | 8 | 0.350 |

Sweet spot: 3-5 PCs. More PCs adds noise back in.

## Key finding
Combining residual subtraction (removes shared component) with PCA (removes noise dimensions) produces dramatically better clusters than either technique alone:
- Raw embedding silhouette: ~0.22
- Residual only (0013): ~0.24
- PCA only (0015): ~0.23
- **Residual + PCA: 0.52-0.60**

The improvement is multiplicative, not additive. Residual removes the mean signal, PCA focuses on the remaining discriminative axes. Together they isolate the behavioral signal.

## Cluster quality at K=10, 5 PCs (silhouette 0.52)
- Inspect (40) — clean separation
- Desperate survival (40) — forage/bake when starving
- Trade evaluation (70) — mixed forage/accept/offer
- Communication-heavy (53) — DMs, offers, negotiations
- Stable production (48) — baking from stability

## Agglomerative also works well
Ward linkage K=8 on 3 PCs: silhouette 0.43. The hierarchical approach could reveal natural cluster counts through dendrogram analysis.

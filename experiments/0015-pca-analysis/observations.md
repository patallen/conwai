# Experiment 0015: PCA Analysis

## Results
Top 5 PCs explain 45.8% of variance. Top 10 explain 60.4%.

### What each PC captures
| PC | Variance | Negative End | Positive End |
|----|----------|-------------|--------------|
| 1 (14.5%) | | Desperate survival (bake, forage) | Inspection/assessment |
| 2 (11.3%) | | Trade rejection | Crisis foraging + inspection |
| 3 (8.6%) | | Governance/voting | Production/inspection |
| 4 (7.1%) | | Crisis baking (zero bread) | Other |

### K-means on PCs
| PCs | Sizes (K=10) |
|-----|-------------|
| 2 | [47,31,28,26,26,25,25,15,14,14] — very balanced |
| 5 | [42,37,32,32,26,24,22,14,14,8] |
| 10 | [40,34,34,32,27,24,24,15,12,9] |
| 20 | [45,35,33,28,26,26,26,14,10,8] |

## Analysis
PCA confirms there IS sub-structure in the embedding space — it's just not visible to cosine similarity because it's along specific axes, not angular separation. The first 2-3 PCs capture meaningful behavioral axes:
- Axis 1: Survival pressure (how desperate is the agent?)
- Axis 2: Trade stance (rejecting vs seeking)
- Axis 3: Social vs productive behavior

Clustering on 2 PCs gives the most balanced clusters — interesting because it uses the smallest representation.

## Key insight
The embedding space has structure, but it's LOW-DIMENSIONAL structure (most variance in just 2-3 axes) embedded in 1024-dimensional space. Cosine similarity in 1024D can't see it because the signal is diluted by 1021 noise dimensions. Projecting to just the top PCs removes the noise.

## New ideas
- Combine PCA with residual vectors: PCA on residuals might be even cleaner
- Use PCA axes as interpretable features (PC1 = "desperation level")
- Adaptive PCA: as new entries arrive, update PCs to capture evolving patterns

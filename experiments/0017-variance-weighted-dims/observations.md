# Experiment 0017: Variance-Weighted Dimensions

## Results
Best strategy: **top 128 dims** (mean sim 0.731, std 0.108 — vs original 0.797, 0.075).

Keeping only the highest-variance dimensions helps modestly. The mean similarity drops and std increases, but not as dramatically as residual vectors (0013).

## Comparison
| Strategy | Mean Sim | Std |
|----------|----------|-----|
| Original (1024D) | 0.7972 | 0.0745 |
| Top 256 dims | 0.7389 | 0.1017 |
| Top 128 dims | 0.7309 | 0.1081 |
| Top 64 dims | 0.7620 | 0.1043 |
| Residual (0013) | -0.003 | 0.228 |

## Analysis
Dimension selection helps but is clearly inferior to residual subtraction. Residual vectors get 3x the std improvement. This makes sense: low-variance dimensions are noise, but high-variance dimensions still contain the shared component. You need to subtract the centroid (residual) to remove the shared signal, not just pick different dimensions.

The top_128_dims clusters are decent (desperate survival, stable baking, urgent messaging) but not as clean as residual clusters from 0013.

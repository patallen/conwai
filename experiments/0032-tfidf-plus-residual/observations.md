# Experiment 0032: Hybrid TF-IDF + Residual Embedding

## Results
| Representation | K=5 sil | K=8 sil |
|---------------|---------|---------|
| TF-IDF only | 0.10 | 0.10 |
| Residual only | 0.25 | 0.24 |
| Residual PCA(5) | 0.55 | 0.52 |
| **Combined PCA(5)** | **0.57** | **0.54** |
| Combined PCA(10) | 0.43 | 0.43 |

## Analysis
Combined slightly better than residual PCA alone (+0.02 silhouette). The TF-IDF features add marginal discriminative value. Not worth the complexity — residual+PCA is already capturing the signal.

PCA(5) sweet spot holds for combined as well. More PCs degrades quality.

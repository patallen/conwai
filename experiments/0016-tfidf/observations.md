# Experiment 0016: TF-IDF Vectors

## Hypothesis
TF-IDF naturally de-emphasizes shared vocabulary via IDF. No embedding model needed.

## Results
- Vocab size: 828 unique words
- Mean pairwise similarity: **0.186** (vs 0.80 for bge-large — 4x more spread out)
- Std: 0.090

### K-means K=10 clusters
Clusters are NOT pure action-type groupings — they mix action types meaningfully:
- Cluster 0 (23): urgent messaging/offers (send_message+offer) — desperation comms
- Cluster 3 (58): desperate survival (forage+bake when starving)
- Cluster 4 (14): stable maintenance (bake+forage when safe)
- Cluster 5 (42): trade-oriented actions (bake+offer+accept)
- Cluster 6 (21): routine foraging (stable, proactive)
- Cluster 7 (40): skeptical trade evaluation (forage+accept)
- Cluster 8 (29): assessment (inspect+vote)

## Analysis
TF-IDF is promising. The entries are much more spread out (mean 0.19 vs 0.80), and K-means produces clusters that capture behavioral context, not just action types. "Desperate foraging" lands in a different cluster from "routine foraging" because the surrounding vocabulary is different (starving, critical, zero vs stable, surplus, proactive).

No embedding model needed — pure word frequency. Fast, cheap, no GPU.

## New ideas
- Combine TF-IDF with embeddings? Use TF-IDF for initial clustering, embeddings for within-cluster refinement.
- TF-IDF on bigrams/trigrams instead of unigrams? "zero bread" and "surplus flour" are more distinctive than individual words.
- Remove stopwords before TF-IDF to sharpen the signal.
- Weight TF-IDF features by action type — what words distinguish forage-while-starving from forage-while-stable?

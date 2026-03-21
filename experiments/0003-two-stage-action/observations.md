# Experiment 0003: Two-Stage Action Clustering

## Hypothesis
Bucketing by action type first, then sub-clustering reasoning within each bucket, would reveal behavioral sub-patterns.

## Results

### Within-Group Pairwise Similarity
| Action Type   | Count | Mean Sim | Std   |
|---------------|-------|----------|-------|
| forage        | 89    | 0.8266   | 0.069 |
| inspect       | 40    | 0.8810   | 0.039 |
| bake          | 39    | 0.8511   | 0.054 |
| offer         | 24    | 0.8556   | 0.042 |
| send_message  | 22    | 0.8594   | 0.054 |
| accept        | 17    | 0.8659   | 0.047 |
| **Overall**   | 251   | 0.7972   | 0.075 |

Within-group similarity is HIGHER than overall (0.83-0.88 vs 0.80). Entries that share an action type are even more similar than the average pair.

### Sub-clustering
At threshold 0.85, most action types remain 1 cluster. Only forage shows some breakup:
- forage@0.90: 16 clusters (32, 19, 12, 7, 4, 3, ...)
- inspect@0.90: 3 clusters (26, 12, 2)
- bake@0.90: 11 clusters (14, 12, 5, ...)

But these are near-duplicate groups, not behavioral patterns.

## Analysis
**Two-stage approach makes the problem WORSE.** Filtering by action type removes the one dimension of variance (what action was taken), leaving only the shared vocabulary and reasoning structure. Within "forage" entries, there's even less diversity than across all entries.

## Key Insight
Action type is the ONLY clear axis of variation in the embedding space. Once you control for it, everything collapses further. This confirms that off-the-shelf embeddings capture topic/vocabulary, not behavioral intent. The LLM abstraction (experiment 0004) is necessary.

# Experiment 0022: TF-IDF with Stopword Removal

## Results
- Shape: (251, 707), mean sim: 0.117 (vs 0.186 raw TF-IDF)
- Stopword removal helps — lower mean similarity
- K=10 clusters: [56,31,27,27,23,22,20,19,14,12] — more balanced than raw TF-IDF

## Cluster quality
Clusters 3 (56 entries: desperate foraging/baking), 4 (27: baking when stable), 6 (31: routine foraging) show behavioral distinction within the same action type. This is promising.

## Key observation
After removing stopwords, domain words (flour, bread, water) dominate every cluster's top words. The signal is in the CO-OCCURRENCE patterns of these words, not in rare distinctive words. "zero + bread + critically" = crisis cluster, "reserves + flour + forage" = maintenance cluster.

## New idea
- Instead of removing domain words (which failed in 0001), weight them differently based on CONTEXT. "zero bread" and "surplus bread" should be far apart even though both contain "bread."

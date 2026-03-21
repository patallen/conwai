# Experiment 0034: Tight Cliques with Pattern Extraction

## Results
127 cliques at threshold 0.80 — but mostly overlapping subsets of the same groups. Inspect entries (40) produce ~15 near-duplicate cliques. Word intersection is too crude.

One real pattern found: Clique 15 (19 entries): "WHEN zero bread+flour → bake"

## Problems
1. Inspect entries are data dumps, not reasoning — should be filtered before clustering
2. Clique algorithm produces overlapping near-duplicates
3. Word intersection misses structural patterns ("I rejected because X" vs "I accepted because Y" share the same words but opposite behaviors)

## Next steps
- Filter inspect entries before processing
- De-duplicate overlapping cliques (merge cliques with >80% shared entries)
- Better pattern extraction: look at sentence STRUCTURE, not just shared words
- Maybe: extract (action_taken, resource_state, social_context) tuples and cluster THOSE

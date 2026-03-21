# Experiment 0039: Incremental Consolidation Pipeline

## Results
The pipeline is stable incrementally. 7 situations emerge and hold from entry ~100 onwards.

| Checkpoint | Situations | Branches |
|-----------|-----------|----------|
| 25 entries | 4 | 11 |
| 50 entries | 4 | 14 |
| 100 entries | 5 | 19 |
| 150 entries | 7 | 29 |
| 200 entries | 7 | 34 |
| 251 entries | 7 | 38 |

Early situations (1-4) are stable throughout — they grow in size but don't restructure. New situations (5-7) emerge as the agent encounters genuinely new conditions later in the sim.

## Key observation
The pipeline works ONLINE:
1. New entry arrives
2. Split into condition + decision sentences
3. Embed both
4. Find nearest existing situation (or create new)
5. Within that situation, find nearest branch (or create new)

No batch reprocessing needed. Each entry is assigned once, situations grow incrementally.

## Limitation
The PCA recomputation happens every entry (expensive). In production, PCA components should be computed once from initial entries and then held fixed, or updated periodically (every 24 ticks).

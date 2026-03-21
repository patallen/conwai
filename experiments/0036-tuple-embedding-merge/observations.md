# Experiment 0036: Embed Tuples and Merge Near-Duplicates

## Results
101 unique patterns → merged into 10 concepts via embedding clustering.

### Merged concepts (highlights)
| Concept | Episodes | Representative Pattern |
|---------|----------|----------------------|
| 3 | 48 | WHEN crisis+no_bread (starvation state) |
| 10 | 34 | WHEN bad_offer+stable DO follow_strategy (reject bad deals from stability) |
| 7 | 22 | WHEN crisis+no_bread DO abandon_caution/eating_raw (crisis behavior change) |
| 4 | 44 | WHEN stable (general stability — too broad) |
| 6 | 20 | WHEN stable DO follow_strategy (stable strategy execution) |
| 9 | 36 | WHEN bad_offer+stable (facing bad offers while stable) |

## What works
- Pattern merging via embedding successfully groups near-duplicate tuples
- Concept 7 and 10 are genuinely useful consolidated knowledge:
  - "When in crisis with no bread, I abandon my usual caution" (7)
  - "When stable and facing bad offers, I follow my strategy and reject" (10)

## What doesn't work
- Concept 4 ("WHEN stable", 44 episodes) is too broad — same problem as K-means categories
- Concepts 3 and 7 overlap heavily — crisis condition vs crisis behavior should be one concept
- The regex extraction still misses nuance

## Key insight
Two-stage approach (extract tuples → embed → cluster) produces better concepts than single-stage embedding clustering because the tuples encode STRUCTURE (condition+behavior), not just vocabulary similarity. But the regex extraction is the weak link.

## The emerging pipeline
1. Extract (condition, behavior) from each entry (robust extraction needed)
2. Embed the extracted patterns
3. Cluster to merge near-duplicates
4. Each cluster = one consolidated concept, reinforced by N episodes
5. The concept description = the most common pattern variant in the cluster

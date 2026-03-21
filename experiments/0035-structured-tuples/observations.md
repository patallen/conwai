# Experiment 0035: Structured (Condition, Behavior) Tuples

## Results
160 unique tuples from 251 entries. 15 patterns appear 3+ times.

### Key patterns found
| Count | Pattern | What it means |
|-------|---------|---------------|
| 19 | WHEN crisis+low_flour+starving+zero_bread | Helen's most common state |
| 7 | WHEN crisis+starving+zero_bread | Same state, variant |
| 6 | DO follow_strategy BECAUSE bad_rate+strategy+surplus | Reject bad offers when stable |
| 4 | WHEN crisis+starving+zero_bread DO abandon_caution | **KEY**: crisis forces personality override |
| 4 | WHEN sufficient DO follow_strategy BECAUSE bad_rate | When stable, stick to strategy |
| 3 | WHEN high_water DO follow_strategy BECAUSE strategy+surplus | Water-rich, follow strategy |

## What works
- Pattern 4 is REAL consolidated knowledge: "when starving and out of bread, I abandon my usual skepticism" — this is an IF-THEN rule learned from 4 separate episodes
- The tuple COUNT is the reinforcement strength — a natural consolidation signal
- No LLM, no embedding model needed for the extraction itself

## What doesn't work
- 160 unique tuples is too fragmented — regex is too brittle
- Near-duplicate tuples don't merge (crisis+low_flour+starving+zero_bread vs crisis+starving+zero_bread)
- Top patterns lack behavior components (19 episodes just have a condition, no "DO X")
- Regex can't capture nuanced conditions ("I was offered worse than 1:1")

## Key insight
The approach is conceptually right: extract (condition, behavior) from entries, count recurring patterns, those counts ARE the consolidation signal. The implementation needs to be more robust than regex — but using the LLM to extract tuples would defeat the purpose.

## Next ideas
- Embed the tuples and cluster THOSE to merge near-duplicates
- Use sentence decomposition (0020) to separate condition sentences from behavior sentences
- Combine: sentence decomposition → tuple extraction → tuple embedding → clustering

# Experiment 0004: LLM-Extracted Behavioral Abstracts

## Hypothesis
LLM-generated 5-10 word behavioral abstracts capture the WHY rather than the WHAT, producing embeddings that cluster into meaningful categories.

## Results

### Embedding Space Comparison
| Metric | Raw Reasoning | LLM Abstracts |
|--------|--------------|---------------|
| Mean pairwise sim | 0.7972 | 0.6856 |
| Std dev | 0.0745 | 0.0913 |
| Min | 0.3336 | 0.4097 |

Mean dropped from 0.80 to 0.69, std increased. Entries are much more spread out.

### Clustering Results
| Threshold | Clusters | Non-singleton |
|-----------|----------|---------------|
| 0.60      | 1        | 1             |
| 0.65      | 2        | 2             |
| 0.70      | 4        | 4             |
| 0.75      | 11       | 7             |
| 0.80      | 30       | 15            |

### Behavioral Patterns at 0.80 (top 10)
1. **Self-sufficiency / reject risky trades** (78 entries) — skeptical refusal
2. **Urgent desperate trades** (34) — starvation-driven exchanges
3. **Verify reliability first** (24) — cautious partner assessment
4. **Survival foraging over trade** (24) — self-reliance in crisis
5. **Accept fair trades** (16) — equitable exchange
6. **Bake for survival** (10) — direct production
7. **Resource conversion** (9) — strategic surplus management
8. **Immediate survival over caution** (8) — breaking character under pressure
9. **Emergency coin spending** (7) — using monetary surplus
10. **Skeptical inspection** (6) — due diligence

## Analysis
**THIS WORKS.** The LLM abstraction is the key transformation. By describing the behavioral pattern in 5-10 words, the LLM strips away specific resource names and agent names, leaving only the intent/motivation. These abstracts embed into a much more spread-out space with real cluster structure.

The biggest cluster (78 at 0.80) is still large — "reject risky trades" is Helen's dominant behavior pattern (she's skeptical). This could potentially be split further with a more specific prompt.

## Key Insight
Pure embedding-based clustering can't work on this data because the entries are genuinely about the same topic. The LLM serves as an ABSTRACTION LAYER that translates situation-specific prose into pattern-level descriptions. This is the missing piece.

## Implications for the system
- The LLM step is necessary — but could be integrated into existing MemoryCompression calls (zero additional cost)
- When compressing memories, include a "behavioral_pattern" field (5-10 words)
- Embed the pattern field, not the full text
- Cluster patterns to discover consolidated concepts

## Remaining questions
- Can we split the largest cluster further?
- Is the full LLM call necessary, or can we approximate with cheaper methods?
- Would batching (5-10 entries per LLM call) work just as well?

# Experiment 0006: Refined Two-Tier Abstracts

## Hypothesis
Having the LLM assign both a 2-3 word CATEGORY and a 5-10 word PATTERN would produce tighter category clusters while preserving pattern detail.

## Results

### 11 Categories (perfectly stable across all thresholds 0.70-0.90)
| Category | Count |
|----------|-------|
| strategic rejection | 60 |
| proactive stockpiling | 52 |
| cautious verification | 44 |
| desperate acquisition | 34 |
| survival crisis | 24 |
| self-reliant production | 18 |
| fair exchange | 10 |
| trust building | 5 |
| strategic acquisition | 2 |
| emergency spending | 1 |
| public signaling | 1 |

### Embedding Space
| Metric | Categories | Patterns |
|--------|-----------|----------|
| Mean sim | 0.6748 | 0.6579 |
| Std dev | 0.1473 | 0.0965 |

Category std is much higher (0.15) — the categories are well-separated in embedding space.

## Analysis
The two-tier approach produces perfectly clean categories. The LLM effectively does the clustering by assigning consistent category labels. Embedding + clustering just confirms what the LLM already decided.

**This further confirms that embeddings are redundant for this task.** The LLM IS the clustering algorithm. The embedding step just validates what the LLM already knows.

## Comparison across LLM experiments
| Exp | Approach | LLM Calls | Categories | Embeddings Needed? |
|-----|----------|-----------|------------|-------------------|
| 0004 | Individual abstracts | 251 | 15 at 0.80 | Yes |
| 0005 | Direct categorization | ~10 | 10 | No |
| 0006 | Two-tier categories | 251 | 11 | No (validates only) |
| 0007 | Batch abstracts | 26 | 13 at 0.75 | Yes |

**Winner: 0005 (direct LLM categorization)** — fewest calls, no embeddings, best pattern descriptions.

## Verdict
Clean result but 251 LLM calls for what 0005 does in 10. The two-tier format IS useful for prompt design (category + pattern), but should be generated via 0005's batch approach, not individually.

# Experiment 0025: Sentiment-Resource Features

## Hypothesis
Hand-crafted features capturing resource state + sentiment context (crisis vs stability) would cluster entries by behavioral pattern, not just action type.

## Results
19 features extracted per entry. K=10 sizes: [45,36,33,31,30,22,19,15,14,6]

### Cluster characterization
| Cluster | Size | Dominant Features | Interpretation |
|---------|------|-------------------|----------------|
| 0 | 31 | crisis_bread=1.0, crisis_flour=0.94 | Crisis foraging/messaging |
| 1 | 36 | stable_bread=1.0, stable_water=1.0 | Stable surplus management |
| 3 | 22 | all crisis flags on | Mixed crisis — baking/accepting under pressure |
| 4 | 30 | stable_bread=1.0, stable_flour=1.0 | Messaging/trading from position of stability |
| 5 | 45 | mixed stable/crisis, has_water=1.0 | Transitional — have some resources, need others |
| 7 | 33 | stable_water=1.0, low crisis | Water-rich trading/evaluation |
| 9 | 14 | low resource features, social_mentions | Social/governance (posts, votes) |

## Analysis
**Most promising non-LLM, non-embedding approach so far.** Features capture what matters: the CONTEXT in which actions are taken. "Foraging while starving" is genuinely different from "foraging while stable" and this representation separates them.

Key strengths:
- No embedding model needed (zero compute)
- No LLM needed
- Features are interpretable
- Clusters have clear behavioral meaning

Key weaknesses:
- Only 19 dimensions — coarse
- Many entries share similar feature vectors (crisis overlaps with stability when both keywords present)
- Features are hand-engineered for this domain — not generalizable

## New ideas
- Add temporal features (early game vs late game, trend direction)
- Add relational features (mentions specific agents by name)
- Combine with TF-IDF: use features for coarse clustering, TF-IDF for within-cluster refinement
- Make features dynamic: track how features change over time (derivative of crisis_level)

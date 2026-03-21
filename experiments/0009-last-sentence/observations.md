# Experiment 0009: Last Sentence Only

## Hypothesis
The last sentence of reasoning (the decision/conclusion) is more semantically distinct than the full reasoning text.

## Results
| Threshold | Clusters | Avg Size | Max Size |
|-----------|----------|----------|----------|
| 0.70      | 206      | 4.8      | 5        |
| 0.75      | 190      | 4.7      | 5        |
| 0.80      | 159      | 4.6      | 5        |

## Analysis
**Opposite of the mega-blob problem.** Last sentences are too situation-specific to cluster meaningfully. We get 206 clusters from 251 entries at 0.70 — almost every entry is its own cluster.

The last sentences ARE genuinely diverse: "I will inspect @Lisa to verify her water stock", "I will ignore Jeffrey's predatory 2:1 flour demand", "I will bake my 5 flour and 5 water into 5 loaves". Each is tied to a specific moment.

## What this tells us
1. The embedding model CAN distinguish between entries when you strip shared context. The mega-blob isn't because the model is bad — it's because full reasoning text has too much shared vocabulary that drowns out the distinctive parts.
2. Last sentences alone are too specific — they capture the action, not the general pattern.
3. The signal we want is somewhere BETWEEN full reasoning (too similar) and last sentence (too unique).

## Ideas for next experiments
- Try combining last sentence with a CATEGORY prefix (e.g., "TRADE: I will send...") to bridge the gap
- Try embedding a REWRITTEN version that strips specifics but keeps intent: "negotiate trade under crisis pressure" vs the specific "I will DM Matthew about 5 bread for 10 water"
- The real insight: we need to embed at the right level of ABSTRACTION, not at either extreme

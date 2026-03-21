# Experiment 0033: Automatic K Selection

## Results
**Silhouette and Calinski-Harabasz both agree: K=6.**

| Method | Optimal K | Score |
|--------|----------|-------|
| Silhouette | **6** | 0.584 |
| Calinski-Harabasz | **6** | 127.7 |
| Elbow | 3 | — |
| Gap statistic | 24 | 1.348 |

Two methods converge on K=6 — strong signal.

## K=6 Clusters
1. **Trade evaluation** (76): assessing offers, accepting/rejecting
2. **Desperate survival** (42): starving, foraging/baking urgently
3. **Active dealing** (41): messaging, offering, paying
4. **Stable production** (29): baking from position of security
5. **Social/proactive** (23): board posts, voting, community building
6. **Assessment** (40): inspecting other agents

## Implications for production
The system can automatically determine how many consolidated concepts to extract. For Helen, 6 concepts emerge naturally from the data. Different agents will have different natural K values — the system should compute it per agent.

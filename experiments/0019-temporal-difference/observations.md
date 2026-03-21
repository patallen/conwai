# Experiment 0019: Temporal Difference Embeddings

## Results
- Temporal diff: mean sim -0.004, std 0.188 (similar spread to residuals)
- K=10 sizes: [31,30,30,28,25,24,23,22,21,16] — **most balanced clusters of any approach**

## Analysis
Very balanced cluster sizes but noisy content — action types are mixed without clear behavioral patterns. The "what changed" signal captures transitions (e.g., going from inspecting to trading) rather than behavioral state. Less useful than residual vectors (0013) for our purpose.

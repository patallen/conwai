# Experiment 0018: Hebbian Simulation

## Results
Mean similarity INCREASED: 0.7972 → 0.8494 after 3 passes. The ball got DENSER.

## Why it failed
The co-recall mechanism recalls the most similar entries — which are already close. Hebbian reinforcement pushes them even closer. It's a positive feedback loop that compresses the space.

Most co-recalled pairs are inspect entries with each other, or trade entries with each other — entries that are already near-duplicates. Reinforcing their similarity doesn't create new cluster structure.

## What would make Hebbian work
1. **Repulsion**: entries NOT co-recalled should be pushed APART. Attraction alone just collapses the space.
2. **Apply to residual vectors**: start from the spread-out residual space (0013), then Hebbian might create tighter within-cluster bonds without collapsing across clusters.
3. **Context-dependent recall**: instead of recalling by raw similarity (which just finds duplicates), recall by SITUATION similarity (e.g., same resource state). Then Hebbian would reinforce behavioral patterns.

## New ideas
- Hebbian on residual vectors with repulsion
- Contrastive Hebbian: co-recalled pairs attract, randomly-sampled pairs repel

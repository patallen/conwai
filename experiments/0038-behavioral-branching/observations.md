# Experiment 0038: Behavioral Branching Detection

## Results
8 situation types identified. All non-inspect situations show behavioral branching — the same condition leads to 2-3 different decision types.

### Highest-variance branch points
| Situation | Episodes | Decision Variance | Branches |
|-----------|----------|-------------------|----------|
| 3: Critical risk, zero bread/flour | 36 | 0.115 | forage(20) vs DM/spend(10) vs bake(6) |
| 7: Strategy says convert surplus | 22 | 0.110 | bake(13) vs forage(4) vs offer(5) |
| 8: Starving, low flour, skeptical | 22 | 0.093 | forage(8) vs spend coins(9) vs bake(5) |

### What the branching reveals
Situation 3 is the richest: when Helen faces "critical risk with zero bread," she has THREE distinct response patterns:
1. **Self-reliant foraging** (20 eps): "forage immediately, don't trust offers"
2. **Social/monetary** (10 eps): "spend coins, DM agents for deals"
3. **Direct production** (6 eps): "bake what I have right now"

This IS consolidated knowledge: "In crisis, I have 3 strategies, and I choose based on available resources (coins, flour, pending trades)."

## Key insight
Behavioral branching within a situation type is MORE useful for consolidation than single-pattern clusters. Instead of "when starving → forage" (one rule), the agent learns "when starving → I have 3 options, I choose based on context." This is richer, more nuanced knowledge.

## The pipeline so far
1. Embed entries, split into condition (first sentence) + decision (last sentence)
2. Residual+PCA on each
3. Cluster CONDITIONS → situation types
4. Within each situation type, cluster DECISIONS → behavioral branches
5. Consolidated knowledge = situation type + its branches + episode counts per branch

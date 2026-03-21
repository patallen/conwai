# Experiment 0012: Integration Prototype

## What it does
Simulates live consolidation during gameplay:
- Every 24 entries: classify new entries into known patterns
- Every 72 entries: rediscover patterns from all accumulated data
- Every 48 entries: generate actionable "lessons learned"

## Results
Successfully processed all 251 entries with 4 pattern rediscoveries. Final state: 7 patterns, all high/medium confidence.

### Final Patterns (after 240 entries)
1. **Skeptical Verification Before Trade** (~65 entries, high)
2. **Prioritize Flour Over Water** (~55 entries, high)
3. **Immediate Baking Upon Thresholds** (~45 entries, high)
4. **Desperation Overrides Strategy** (~40 entries, high)
5. **Rigid 1:1 Exchange Rates** (~35 entries, high)
6. **Target-Based Stability** (~30 entries, medium)
7. **Coin-Backed Emergency Procurement** (~25 entries, medium)

### Lessons Evolution
Early lessons (24 entries): generic advice about verification and raw flour consumption
Mid lessons (96 entries): specific thresholds (15+ bread, 20+ flour), water conservation
Final lessons (240 entries): refined rules with specific ratios and threshold values

The lessons became MORE SPECIFIC over time as the LLM saw more data. This is exactly what consolidation should do.

### Final Lessons (ready for prompt injection)
1. "Never accept a trade offer immediately; verify partner reliability first"
2. "Trade water surplus for flour aggressively, but refuse non-1:1 rates"
3. "Bake immediately when flour and water are secured"
4. "Abandon skepticism when hunger is critical and bread is zero"
5. "Monitor against thresholds: 20+ bread, 30+ flour"

## Analysis
**The full pipeline works.** Pattern discovery, incremental classification, lesson synthesis, and refinement all function correctly during simulated live gameplay.

Key properties:
- **Convergent**: Lessons become more specific over time
- **Adaptive**: Patterns rediscovered periodically to capture evolution
- **Actionable**: Lessons are in second-person imperative form, ready for prompt injection
- **Efficient**: ~4 LLM calls per consolidation cycle (1 classify + occasional rediscovery + lesson synthesis)

## Integration Design
```
Every 24 ticks (during StrategicReview or MemoryCompression):
  1. Collect diary entries since last consolidation
  2. If no patterns exist yet (first time):
     - LLM discovers 5-10 patterns from all entries
  3. Classify new entries into existing patterns
  4. Every 72 ticks: rediscover patterns from full diary
  5. Synthesize lessons → inject into agent prompt as "behavioral wisdom"
```

Total LLM overhead per consolidation: 1-2 additional calls (classify batch + optional rediscovery)

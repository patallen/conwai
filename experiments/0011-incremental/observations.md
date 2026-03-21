# Experiment 0011: Incremental Consolidation

## Hypothesis
Patterns discovered from the first half of the diary are stable enough to classify the second half. Tests incrementality for live gameplay.

## Results
- First half: 125 entries → 10 patterns discovered
- Second half: 126 entries classified using first-half patterns
- **All 10 patterns reused** — no patterns died, no first-half-only patterns
- **13 entries (10.3%) marked NEW** — all were raw inspect profile dumps, not reasoning

### Distribution Shift (behavioral evolution over time)
| Pattern | First Half | Second Half | Shift |
|---------|-----------|-------------|-------|
| 3 (most increased) | 11.2% | 22.2% | +11.0% |
| 2 | 6.4% | 14.3% | +7.9% |
| 5 (most decreased) | 9.6% | 1.6% | -8.0% |
| 10 | 14.4% | 8.7% | -5.7% |

## Analysis
**Incremental consolidation works.** Patterns are stable across the full diary timeline.

Key findings:
1. **Pattern stability**: First-half patterns cover 90% of second-half entries
2. **Behavioral evolution**: The distribution shifts are meaningful — Helen's behavior changes over time (less of some patterns, more of others). This is exactly what consolidation should capture.
3. **NEW detection**: The 10% "new" entries are almost all inspect dumps (no reasoning). In production, these should be filtered before consolidation.

## Implications for integration
- Discover patterns once (after ~20-30 diary entries)
- Classify new entries incrementally (every 24 ticks)
- Rediscover patterns periodically (every ~72 ticks) to capture evolution
- Filter inspect dumps before processing
- Track distribution shifts to detect behavioral changes

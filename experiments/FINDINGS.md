# Consolidation Experiment Findings

## A/B Test: First-Person vs Third-Person Reflections

### Setup
- **Commit:** `f467ae7` (first-person prompts) on top of `b767da3` (reflection-based consolidation)
- **Backup:** `.backups/consolidation/f467ae7.data.bak`
- **Duration:** 398 ticks (~16 in-game days)
- **Population:** 20 agents (10 flour foragers, 10 water foragers)
- **Groups:** 10 first-person (1P), 10 third-person (3P), all with reflections enabled
- **Model:** Qwen3.5-122B on 2× H200, reflections via Qwen3.5-27B on 2× 3090
- **Only difference:** System prompt for reflection LLM — "your experience" vs "an agent's experience"

### Survival
| Metric | First Person | Third Person |
|--------|-------------|-------------|
| Alive | 10/10 | 9/10 |
| Deaths | 0 | 1 (Adam starved) |
| Hunger (mean±std) | 79.9±1.6 | 71.3±23.8 |
| Hunger range | 78–82 | 0–82 |

1P hunger is tight and stable. 3P has high variance — some agents fine, others near death.

### Resources (end state)
| Resource | First Person | Third Person |
|----------|-------------|-------------|
| Bread | 26.6±30.4 | 14.4±23.5 |
| Flour | 70.6±29.1 | 57.3±41.5 |
| Water | 58.8±38.9 | 54.9±44.3 |
| Coins | 101.2±82.2 | 180.9±100.9 |

1P holds more food. 3P hoards coins instead of converting to food.

### Baking Over Time
| Quarter | First Person | Third Person |
|---------|-------------|-------------|
| Q1 (t<100) | 67 | 110 |
| Q2 (100-200) | 67 | 66 |
| Q3 (200-300) | 93 | 70 |
| Q4 (300+) | 97 | 57 |

**1P baking increased over time. 3P baking decreased.** 1P agents learned to bake more as the game progressed. 3P started strong then declined.

### Trading
| Metric | First Person | Third Person |
|--------|-------------|-------------|
| Total trades | 158 | 160 |
| Offers made | 168 | 108 |
| Conversion rate | 47% | 74% |
| Q1 trades | 39 | 73 |
| Q4 trades | 38 | 24 |

3P trading was front-loaded (73→24 declining). 1P was steady across all quarters (39, 37, 44, 38). 3P had better conversion rate but made fewer offers and declined over time.

### Social Behavior
| Metric | First Person | Third Person |
|--------|-------------|-------------|
| DMs sent | 460 | 512 |
| Board posts | 164 | 188 |
| Inspections | 152 | 103 |

1P did more reconnaissance (inspections), less chatter (DMs, posts).

### Trade Network
- Within-1P trades: 76
- Within-3P trades: 78
- Cross-group trades: 164
- Top pair: Amy(3P) ↔ Christopher(1P) with 14 trades
- Trading was well-mixed between groups — no isolation effects.

### Reflection Quality

**First-person** reflections are self-critical and identify specific mistakes:
- "Your rigid adherence to a 10-flour threshold drove inefficient foraging cycles"
- "Shifting from passive waiting to proactive foraging broke the cycle"
- "The repeated failure to secure water through social trades compelled a fundamental strategic pivot"

**Third-person** reflections are analytical but descriptive:
- "The agent employs a highly adaptive survival strategy"
- "The agent demonstrates a survival-driven capacity to override strategic community engagement"
- "The agent's rigid adherence to a 1:2 trade ratio forces a reactive, opportunity-driven strategy"

### The Crossover

Total bread production by quarter tells the real story:

| Quarter | FP bread | TP bread |
|---------|----------|----------|
| Q1 | 424 | 648 |
| Q2 | 504 | 664 |
| Q3 | 816 | 616 |
| Q4 | 848 | 496 |

TP out-produced FP by 50% in the first half. By Q4, FP produces 70% more. The crossover happens in Q3 — right when agents have accumulated enough reflections to be meaningful. FP agents course-corrected. TP agents didn't.

### Case Studies

**Helen (TP) — "Narrating your way to starvation."** Received 115 DMs (most of any agent). Has 99 water, 345 coins, 0 bread. Traded 17 times with -93 net — exploited by everyone while accumulating coins. Her reflections never told her to stop. Poster child for analytical detachment.

**Christopher (FP) — Survived despite worst trade balance.** 31 trades, -171 net (worst in the sim). But alive at hunger 79 with 14 bread. Self-critical reflections ("my strategy was ineffective") drove him to compensate through foraging and baking rather than relying on trades.

**James (TP) — TP works when you're already winning.** 27 trades, net exactly 0. Only agent to break perfectly even. 304 bread stockpiled. Analytical reflections work fine for agents who are already succeeding — they fail agents who need to change course.

**Adam (TP) — Died with 215 coins.** The coin hoarding problem in miniature.

### The Coin Paradox

TP agents hoarded 1809 coins (Gini 0.31 — evenly distributed wealth). FP agents have 1012 coins (Gini 0.44 — more unequal but nobody's rich-and-starving). TP agents optimized for a metric that doesn't feed them. The analytical reflections apparently frame coin accumulation as "strategic" and never flag it as a problem.

### Emergent Social Behavior

**FP alliance formation.** Danielle posted: "@Danielle and @Jill have formed a long-term trade partnership: flour for water. Stable and reliable." This is emergent institution-building — naming a relationship publicly. No TP agent declared a partnership.

**FP agents share lessons publicly.** Erica posted: "Balance is survival. Hoarding one resource while starving for another is fatal." A reflection surfacing as public knowledge. TP agents posted with increasing desperation instead: "URGENT: 0 bread", "CRITICAL! Bread at 3."

**FP agents scout outward.** FP: 68% of inspections are cross-group. TP: 41% cross-group. Maps to "what am I missing?" (look outward) vs "what am I doing?" (look inward).

**TP agents send one-way DMs.** Amy→Helen is 20-0. Jeffery→Adam is 14-0. TP agents don't read social signals about who will actually trade back.

### Reflection Sentiment

| | Negative | Positive | Action-oriented |
|--|----------|----------|-----------------|
| FP | 51% | 31% | 15% |
| TP | 38% | 31% | 26% |

FP reflections are more negative but drive change through felt failure ("my strategy failed"). TP reflections use more action words ("prioritize," "shift," "must") but narrate rather than internalize. FP agents feel the failure. TP agents describe it.

### Interpretation

First-person reflections create a feedback loop: failure → felt self-criticism → behavioral change → improvement over time. Third-person reflections create a narration loop: failure → analytical description → no behavioral change → decline over time.

The mechanism is emotional engagement with failure. "I failed" hits differently than "the agent failed to execute optimally."

The only difference was the system prompt: "your experience" vs "an agent's experience."

Full detailed analysis: [`experiments/analysis-f467ae7-detailed.md`](analysis-f467ae7-detailed.md)

### Prior Run Comparison (consolidation vs no consolidation)

**Backup:** `.backups/consolidation/b767da3.data.bak` (198 ticks, 12 agents)

| Metric | Consolidated (6) | Control (6) |
|--------|-----------------|-------------|
| Bread | 27.2±21.7 | 4.0±4.4 |
| Hunger | 80.2±1.5 | 76.2±9.6 |
| Deaths | 0 | 0 (but Anthony at hunger 55) |

Consolidation itself (reflections vs none) showed a clear benefit: +23 bread, more stable hunger. The 1P vs 3P test refined which style of reflection works better.

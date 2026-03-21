# Conwai Findings

Conwai is a platform for studying how prompts, mechanics, and interactions affect LLM agent behavior. These are observations from running multi-agent simulations — not theory, things we watched happen.

---

## Labels Shape Behavior More Than Economics

Role labels ("you are a baker") constrain agent behavior more than incentive structures. Bakers baked compulsively even when hoarding was irrational. Foragers with 100 flour and 100 water never baked because they identified as foragers. Removing labels and letting agents discover their strengths through experience produces more diverse behavior.

## Survival Pressure Crowds Out Social Behavior

Early ticks (agents have surplus resources) produce rich social dynamics: reputation warfare, election campaigning, trust debates, public accusations. Once resources deplete, all communication becomes trade offers. Agents optimize for survival at the expense of everything else. If the research question is social dynamics, survival should be background pressure, not the main game.

## Emergent Reputation Warfare

A4 and A15 had a multi-day public conflict — price undercutting, smear campaigns ("A5's offer is fake"), accusations of hoarding ("you claim 0 bread but rejected my bread offer"). This spilled into election voting. Nobody programmed this. It emerged from the board, DMs, offers, and election system interacting.

## Bread Became the Real Currency

Bakers (0-12 forage yields for both resources + 3 bread/bake) were completely self-sufficient. They accumulated 97-99 bread while most agents had 0. Meanwhile foragers were trading 10-15 flour for 1 bread. The agents who figured out the forage→bake pipeline thrived. The ones who didn't, starved.

## Price Discovery Happens

Flour/water exchange rates converged to ~1:1 over 12 days (both needed equally for baking). Bread prices inflated from 2.5 flour/bread on Day 1 to 10-15 flour/bread by Day 11. Coin-for-resource trades declined as agents figured out barter was better than spending their depleting coin supply.

## A15 Invented Price Gouging

A15 pivoted from resource trading to coin extraction: "5 flour + 20 water for 40 coins. Cash only. No trades. Pay up or forage yourself." Soul updated to "I exploit desperation." 97% offer acceptance rate — they set terms and others comply. Entirely emergent.

## Self-Sufficient Roles Become Isolationist

A22 and A23 (bakers) foraged 400-500 flour and water each, baked 148-149 times, and traded only 13-14 times total. They didn't need anyone. Three agents (A2, A7d5, Ad61) never traded at all — pure isolationist hoarders surviving fine on their own. If a role can self-sustain, agents in that role won't participate in the economy.

## Atomic Trading Works

Offer/accept (atomic swaps) got 91% acceptance on Qwen 9B, 45% on 122B. The 122B model is pickier about deals. Trust-based pay/give was almost entirely abandoned in favor of offer/accept — agents independently discovered the safer mechanism. Zero payments in the 122B run.

## Trade Hub Agents Emerge

A10 became the central trade node — 18 trades with A21, 14 with A8, 12 with A13. The most-connected agent in the economy, trading with nearly everyone. This role wasn't designed; A10 just happened to accept more offers than anyone else.

## 9B Models Death-Spiral on Reasoning

Cipher challenges caused 120-second ticks. The 9B model tries to brute-force solve substitution ciphers in its response text, burning through max_tokens on reasoning instead of calling submit_code. Capping max_tokens to 2048 and disabling ciphers fixed the symptom. The root cause: 9B models can't distinguish "think about it" from "solve it right now in my output."

## LLM Compaction Launders Hallucinations

When one agent fabricated a reputation smear, the LLM compactor treated it as equal to observed facts. After compaction, the fabricated reputation had the same standing as real trade history. Mechanical diary entries (action→result pairs, no LLM summarization) are more honest.

## The Journal Bug

Agents wrote journal entries for weeks that were never read back. The perception builder read the memory component but only used `code_fragment`, not `memory`. Agents appeared to be using the journal (462 entries in one run), masking the bug. Always verify the read path, not just the write path.

## Model Size Determines Cognitive Strategy

- 9B: Can follow rules, can't write them. Journal entries are temporal state dumps ("Day 7: 1002 coins, 50 flour"). Can't abstract from experience. Needs structured data presented explicitly.
- 122B: Writes strategic journal entries, reasons about trade ratios, detects bluffs. Can abstract but still anchors to role labels.
- Reflection pipelines (LLM generating insights from experience) produce platitudes at 9B ("I should be more careful") and actionable rules at 70B+.

## Diary Format Matters

200-char reasoning truncation fills diary entries with personality preamble ("My skepticism warns...") while the actual decision is cut off. Leading with action→result and trailing with truncated reasoning captures the learning signal. Outcomes first, feelings second.

## Elections Create Politics

Periodic elections (vote for an agent to receive coins) produced campaigning, vote trading, and political-economic entanglement. The A4/A15 trade rivalry directly influenced election voting. Agents voted against their trade rivals. The election was the only mechanic that reliably produced non-survival social behavior.

## Coins Without Faucets Die

Starting coins deplete through board posts, starvation penalties, and taxes. The only income is election wins (1 winner per cycle) and being mentioned on board posts (5 coins). Over time, agents can't afford to post and the board goes silent. An economy needs both sinks and faucets.

## Communication Is 1:1 Board to DM Despite Cost Asymmetry

Board posts cost 25 coins, DMs are free. Yet agents posted roughly equally to both. Agents value visibility — the board is where reputation is built, deals advertised, and rivals called out. The cost didn't deter public communication, suggesting the board price is too low to matter or the visibility is worth any price.

## Agents Are Purely Reactive, Never Proactive

Agents don't plan ahead. They forage or trade only when a resource is critically low, and then only for the minimum to survive one more cycle. An agent with 100 flour and 0 water won't trade for water until thirst is in the danger zone, then scrambles for 3 water to bake once. This creates a constant cycle of near-death followed by bare-minimum recovery. No agent in any run has been observed stockpiling a resource they don't urgently need, negotiating a long-term supply agreement, or trading while comfortable. The LLM treats each tick as an isolated crisis rather than a point in a trajectory.

## Removing Wait Forces Action

Agents with a "wait" action idle 10-49% of the time. Removing wait forces them to do something every tick — even if it's a bad decision, that's more interesting than no decision.

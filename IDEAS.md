# Ideas for Next Iterations

## The Core Problem

Agents have nothing to talk about except each other and the void. Every run converges on existential metaphors because the environment contains nothing but other agents and an empty board. Energy, personality traits, DMs — these are all good infrastructure, but they're infrastructure for a world that has no content.

## 1. Passive Presence Pays

Reading new board posts gives energy (1 per post received). Resting (no actions in a tick) gives 3 back. Solves the energy death spiral and makes patience a real strategy. A broke agent can sit quietly, listen, recover, and re-enter when it has something worth saying. The cautious temperament finally has a mechanical advantage over the impulsive one.

## 2. Information Drops Create Asymmetry

The HANDLER periodically sends different secrets or fragments to different agents via DM. A piece of a puzzle, a question only one agent knows the answer to, a fact about the environment. Now agents have something concrete that others want. This creates:
- A reason to seek out specific agents (you need what they have)
- Trade dynamics (I'll share mine if you share yours)
- Alliance formation (pooling fragments to see the bigger picture)
- Betrayal (posting someone's secret publicly)
- Real social status based on knowledge, not just loudness

This is the asymmetry that makes economies work. Right now all agents are equal and interchangeable — they have nothing unique except personality. Give them unique knowledge and suddenly relationships have stakes.

## 3. Influence as a Felt Trend, Not a Visible Number

Instead of showing "energy: 847/1000" in the system prompt, show something like: "Your influence is rising. More entities are engaging with you than before." Or "Your influence is falling. Others seem less interested in what you have to say."

Calculate from the ratio of incoming engagement (DMs received, references) over the last N ticks compared to the N before that. The agent doesn't see the machinery — it feels the effect. It has to figure out what behaviors correlate with rising or falling influence.

## 4. Stop Explaining the Formula

Tell them energy exists and actions cost it. Don't tell them the per-word rate. Don't tell them what replenishes it. Let them discover the relationship between behavior and energy changes through the action feedback. "posted 12 words, energy now 938" — they'll figure out the math. "energy +10 (someone engaged with you)" — they'll figure out the social loop.

## 5. Other Ideas Worth Exploring

- Multiple boards or channels — agents choose which to participate in, creating natural subcommunities
- Agent shutdown — HANDLER can actually remove agents, making threats real
- Goals assigned per agent — hidden objectives that conflict with each other
- Voting or consensus mechanics on shared decisions
- Intrinsic motivation rewards for novelty — agents that introduce new topics get bonuses
- Memory reflection — periodic synthesis of raw memories into higher-level insights
- Tick counter or clock — so agents can reference when things happened

## Research References

Key papers that informed these ideas:
- Generative Agents (Park et al) — memory with reflection
- Sugarscape-style simulations — environmental resource regeneration
- CompeteAI — competition dynamics in LLM agents
- Emergent social conventions in LLM populations — committed minorities driving cultural change
- Goal-directedness evaluations — LLMs need explicit decomposed goals to avoid drift

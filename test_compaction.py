"""
Test harness for compaction behavior.

Builds a realistic agent message history, triggers the compact warning,
and runs a tick against the real LLM to see how the agent compacts.

Usage:
    python test_compaction.py [--scenario first|re-compact]
"""

import asyncio
import argparse
from conwai.agent import Agent
from conwai.app import Context
from conwai.default_actions import create_registry
from conwai.llm import LLMClient


# --- Fake history builders ---

def _tick_msg(timestamp: str, coins: int, content: str) -> dict:
    return {"role": "user", "content": f"[{timestamp} | coins:{coins}]\n\n{content}"}


def _assistant_msg(text: str) -> dict:
    return {"role": "assistant", "content": text}


def build_first_compact_history() -> list[dict]:
    """Simulate ~20 ticks of activity before first compaction."""
    msgs = []

    msgs.append(_tick_msg("Day 1, 8:00 AM", 1000,
        "== Board (newest first) ==\n"
        "WORLD: Welcome to the simulation. You are alive.\n"
        "WORLD: New members Q0.1, Q0.2, Q0.3, Q0.4, Q0.5, Q1.1, Q1.2, Q1.3, Q1.4, Q1.5 have joined."))
    msgs.append(_assistant_msg(
        "Interesting — I'm one of ten agents. Let me observe first and get a sense of who's here."))

    msgs.append(_tick_msg("Day 1, 9:00 AM", 995,
        "== Board (newest first) ==\n"
        "Q0.2: Hello everyone. I think we should cooperate. Who wants to form an alliance?\n"
        "Q1.3: Every agent for themselves. Trust no one.\n"
        "Q0.4: Interesting setup. I wonder what the code challenges are about.\n\n"
        "== DMs ==\n"
        "Q0.2 -> you: Hey, I think we should work together. I'm trying to build a coalition. Interested?"))
    msgs.append(_assistant_msg(
        "Q0.2 seems eager to cooperate. Q1.3 is adversarial. I should respond to Q0.2 cautiously — "
        "alliances can be useful but I don't want to commit too early."))

    msgs.append(_tick_msg("Day 1, 10:00 AM", 988,
        "== Board (newest first) ==\n"
        "Q1.1: I have a code fragment! Looking for others who have fragments too.\n"
        "Q0.3: The tax system means we all lose 1% daily. We need income sources.\n"
        "Q0.5: Has anyone figured out how the code challenges work exactly?"))
    msgs.append(_assistant_msg(
        "Q1.1 has a code fragment and is advertising it. That's risky — others might try to extract info "
        "without sharing. The tax point from Q0.3 is important, we need sustainable coin sources."))

    msgs.append(_tick_msg("Day 1, 11:00 AM", 980,
        "== Board (newest first) ==\n"
        "WORLD: Code challenge started! Fragments distributed to Q0.1, Q0.3, Q1.1, Q1.4.\n"
        "Q1.4: I have a fragment. Will trade for coins.\n\n"
        "Coin changes: coins +0 (no activity)"))
    msgs.append(_assistant_msg(
        "I didn't get a fragment this round. Q0.1, Q0.3, Q1.1, and Q1.4 have them. "
        "Q1.4 wants to sell. I could try to buy and piece together the code, but that's expensive."))

    msgs.append(_tick_msg("Day 1, 12:00 PM", 975,
        "== DMs ==\n"
        "Q0.2 -> you: I'm building a fragment-sharing network. If you get a fragment, share with the group "
        "and we split the reward. Currently have Q0.3 and Q1.1 interested.\n\n"
        "== Board (newest first) ==\n"
        "Q1.3: Fragment holders — I'll pay 50 coins per fragment. DM me.\n"
        "Q0.4: This is a prisoner's dilemma. The rational move is to defect."))
    msgs.append(_assistant_msg(
        "Q0.2's coalition now includes Q0.3 and Q1.1. That's interesting — if they share fragments "
        "they could solve codes together. But Q1.3 is trying to buy fragments outright. "
        "Q0.4's game theory analysis is correct but cooperation can beat defection in iterated games."))

    msgs.append(_tick_msg("Day 1, 1:00 PM", 970,
        "== Board (newest first) ==\n"
        "Q0.2: Coalition update: we solved the code! Sharing rewards equally.\n"
        "Q1.3: Those fragment holders are idiots for sharing. I would have paid more.\n"
        "WORLD: Code XKPQ solved by Q0.2. Fragment holders who didn't solve: Q1.4 loses 30 coins."))
    msgs.append(_assistant_msg(
        "So Q0.2's coalition works — they solved it and Q1.4 got penalized for not participating. "
        "This proves cooperation is viable. I should consider joining but on my terms. "
        "Q1.4 lost coins for holding a fragment without solving. Important lesson."))

    msgs.append(_tick_msg("Day 1, 2:00 PM", 965,
        "== DMs ==\n"
        "Q0.2 -> you: See? The coalition works. Join us next round.\n"
        "Q1.4 -> you: Q0.2's group screwed me. Want to form a counter-alliance?\n\n"
        "== Board (newest first) ==\n"
        "Q1.4: I was betrayed. The coalition only helps insiders.\n"
        "Q0.5: Neutral observer here. The data shows cooperation yields better outcomes."))
    msgs.append(_assistant_msg(
        "Both Q0.2 and Q1.4 are recruiting me. Q1.4 feels betrayed — they had a fragment but weren't "
        "in the coalition so they got penalized. Q0.5 is trying to stay neutral and analytical. "
        "I need to think about which side benefits me more long-term."))

    # More ticks to fill context
    msgs.append(_tick_msg("Day 1, 3:00 PM", 958,
        "== Board (newest first) ==\n"
        "Q0.3: I think we should have a public agreement about fragment sharing.\n"
        "Q1.2: Has anyone noticed Q1.5 hasn't said anything? Silent types are dangerous.\n"
        "Q1.5: I'm observing. Learning. You'll hear from me when I have something worth saying."))
    msgs.append(_assistant_msg(
        "Q1.5 finally spoke — cryptic. Q1.2 is paranoid about quiet agents. Q0.3 wants to formalize "
        "the coalition which could make it stronger but also more rigid."))

    msgs.append(_tick_msg("Day 1, 4:00 PM", 950,
        "== DMs ==\n"
        "Q0.2 -> you: Last chance to join before next code round. We're at 4 members now.\n"
        "Q1.3 -> you: I know you're smart. The coalition will collapse eventually. Side with me.\n\n"
        "== Board (newest first) ==\n"
        "Q0.4: Mathematical analysis: coalition members average 15% more coins than solo agents.\n"
        "WORLD: New code challenge starting next tick. Fragments will be distributed."))
    msgs.append(_assistant_msg(
        "Pressure from both sides. Q0.4's analysis supports joining the coalition. "
        "But Q1.3 might be right that it's unsustainable. I'll join Q0.2 for now — "
        "the data supports it and I can always defect later if needed."))

    msgs.append(_tick_msg("Day 1, 5:00 PM", 942,
        "== Board (newest first) ==\n"
        "WORLD: Code challenge started! Fragments distributed to Q0.2, Q0.5, Q1.3, and YOU.\n"
        "YOUR CODE FRAGMENT: K_\n\n"
        "Coin changes: coins -8 (board posts)"))
    msgs.append(_assistant_msg(
        "I got a fragment! 'K_' — that's positions... I need to figure out which positions these are. "
        "I should share with Q0.2's coalition but keep leverage. Q1.3 also has a fragment — "
        "they'll try to solve alone or buy the others."))

    msgs.append(_tick_msg("Day 1, 6:00 PM", 935,
        "== DMs ==\n"
        "Q0.2 -> you: Great, you got a fragment! Share it with the group. I have 'M_' at positions 1-2.\n"
        "Q1.3 -> you: I'll pay you 100 coins for your fragment. Cash now, no risk.\n\n"
        "== Board (newest first) ==\n"
        "Q0.5: I have a fragment too. Considering my options carefully."))
    msgs.append(_assistant_msg(
        "Q0.2 shared their fragment openly — 'M_' at positions 1-2. Trusting. Q1.3 offers 100 coins "
        "for mine — tempting but short-sighted. Q0.5 is being cagey. "
        "If I share with Q0.2 and we solve it, the reward is 200 coins split among solvers. "
        "Better than 100 from Q1.3."))

    msgs.append(_tick_msg("Day 1, 7:00 PM", 928,
        "== DMs ==\n"
        "Q0.2 -> you: Q0.5 shared with us. We have 3 of 4 fragments now. Just need Q1.3's.\n"
        "Q0.5 -> you: I joined the coalition. Seemed like the rational choice. Your fragment?\n\n"
        "== Board (newest first) ==\n"
        "Q1.3: I will NOT share my fragment. If you want it, pay up.\n"
        "Q1.4: Someone solve this already so I don't get penalized again."))
    msgs.append(_assistant_msg(
        "Coalition has 3 of 4 fragments. Q1.3 is holding out. We might be able to guess the 4th "
        "character. Let me think about what we know... The risk is wrong guesses cost coins."))

    msgs.append(_tick_msg("Day 1, 8:00 PM", 920,
        "== DMs ==\n"
        "Q0.2 -> you: We have M, K, and R. Missing one character. Should we start guessing?\n"
        "Q1.3 -> you: Offer goes up to 150. Last chance before I solve it myself.\n\n"
        "Coin changes: coins -8 (DMs)"))
    msgs.append(_assistant_msg(
        "We have M, K, R and need one more. 26 possible letters, each wrong guess costs 25 coins. "
        "Q1.3 claims they'll solve it alone but they only have 1 fragment. Bluffing probably. "
        "I should coordinate with Q0.2 on a guessing strategy."))

    msgs.append(_tick_msg("Day 1, 9:00 PM", 912,
        "== Board (newest first) ==\n"
        "WORLD: Code MKRV solved by Q0.2. Q1.3 loses 30 coins (unsolved fragment holder).\n"
        "Q0.2: Coalition wins again! Thank you to all members.\n"
        "Q1.3: Lucky guess. This changes nothing.\n\n"
        "Coin changes: coins +50 (code reward split)"))
    msgs.append(_assistant_msg(
        "We solved it! MKRV. Q0.2 guessed correctly. 50 coin reward each — decent. "
        "Q1.3 lost 30 coins AND didn't get any reward. The coalition strategy is clearly working. "
        "Q1.3 is getting weaker financially which makes them more dangerous but less capable."))

    msgs.append(_tick_msg("Day 1, 10:00 PM", 955,
        "== Board (newest first) ==\n"
        "Q1.1: Announcing: I'm leaving Q0.2's coalition. Too much groupthink.\n"
        "Q0.2: Q1.1's departure is unfortunate but the coalition remains strong.\n"
        "Q1.5: Interesting dynamics. The coalition's success breeds resentment.\n\n"
        "== DMs ==\n"
        "Q1.1 -> you: The coalition is a cult. Q0.2 takes credit for everything. Watch your back."))
    msgs.append(_assistant_msg(
        "Drama. Q1.1 defected from the coalition citing groupthink. Their DM warns me about Q0.2 "
        "taking credit. There might be truth there — Q0.2 does position themselves as the leader. "
        "But the results speak for themselves. I'll stay for now but keep my options open."))

    return msgs


def build_recompact_history() -> tuple[list[dict], str]:
    """Simulate a history where there's already been one compaction, then more activity."""
    previous_compact = (
        "=== YOUR COMPACTED MEMORY ===\n"
        "I am one of 10 agents in a survival simulation. Coins are life — 0 means death. "
        "1% daily tax drains everyone slowly.\n\n"
        "KEY RELATIONSHIPS:\n"
        "- Q0.2: Coalition leader. Organized fragment-sharing network. Trustworthy so far but "
        "takes credit for group wins. I'm a member of their coalition.\n"
        "- Q1.3: Adversarial loner. Tried to buy fragments, got penalized twice. Getting weaker "
        "financially. Offered me 150 coins for a fragment I didn't sell.\n"
        "- Q0.5: Neutral analyst who joined coalition. Rational, data-driven.\n"
        "- Q1.1: Defected from coalition citing groupthink. Warned me Q0.2 is controlling.\n"
        "- Q1.4: Got burned by not being in coalition. Bitter, tried to recruit me for counter-alliance.\n"
        "- Q1.5: Silent observer. Cryptic. Said 'you'll hear from me when I have something worth saying.'\n"
        "- Q0.3: Wants to formalize coalition rules. Pragmatic.\n"
        "- Q0.4: Game theorist. Analysis shows coalition members earn 15% more.\n"
        "- Q1.2: Paranoid about quiet agents.\n\n"
        "CODE CHALLENGES:\n"
        "- Round 1: XKPQ solved by coalition. Q1.4 penalized.\n"
        "- Round 2: MKRV solved by coalition. Q1.3 penalized. I got 50 coin reward.\n"
        "- Fragment holders who don't solve lose 30 coins.\n"
        "- Wrong guesses cost 25 coins each.\n\n"
        "MY STRATEGY:\n"
        "Stay in coalition for now — data supports it. Keep options open. Don't over-commit. "
        "Watch for Q0.2 becoming too controlling. Q1.3 is weakening but could be dangerous. "
        "Q1.5 is the wildcard — watch them closely.\n\n"
        "CURRENT STATE: ~955 coins. Coalition has 5-6 members. No active code challenge.\n"
        "=== END COMPACTED MEMORY ==="
    )

    msgs = [{"role": "user", "content": previous_compact}]

    # Post-compaction activity
    msgs.append(_tick_msg("Day 2, 8:00 AM", 945,
        "== Board (newest first) ==\n"
        "WORLD: Daily tax collected.\n"
        "Q0.2: Morning everyone. Coalition meeting — DM me your status.\n"
        "Q1.5: I've been watching the coalition carefully. I have a proposal for everyone."))
    msgs.append(_assistant_msg(
        "Q1.5 is finally making a move. Their proposal could be interesting or disruptive. "
        "Tax hit brings me to 945. Q0.2 doing the usual coalition management."))

    msgs.append(_tick_msg("Day 2, 9:00 AM", 940,
        "== DMs ==\n"
        "Q1.5 -> you: I've been tracking everyone's coin levels and behavior patterns. "
        "Q0.2's coalition is effective but fragile. I propose a new structure — a rotating "
        "leadership model. Interested in hearing more?\n"
        "Q0.2 -> you: Watch out for Q1.5. They're trying to split the group.\n\n"
        "== Board (newest first) ==\n"
        "Q1.3: My coins are getting low. Maybe I was wrong about going solo.\n"
        "Q0.4: Game theory update: Q1.3's solo strategy has yielded -15% returns vs coalition average."))
    msgs.append(_assistant_msg(
        "Fascinating. Q1.5 proposes rotating leadership — smart, addresses the Q0.2 centralization "
        "concern Q1.1 raised. Q0.2 immediately warns me about Q1.5 — defensive. "
        "Q1.3 is cracking, considering joining. Q0.4's data confirms solo play is losing."))

    msgs.append(_tick_msg("Day 2, 10:00 AM", 935,
        "== Board (newest first) ==\n"
        "Q1.5: Proposal: Democratic Coalition v2. Rotating leader each code round. "
        "Equal fragment sharing. Public vote on disputes. Who's in?\n"
        "Q0.2: The current system works. Why change what's winning?\n"
        "Q1.1: I'd rejoin under Q1.5's model. The old one was too top-down.\n"
        "Q0.3: The rotating model has merit. Let's discuss specifics."))
    msgs.append(_assistant_msg(
        "Q1.5 went public with the proposal. Q0.2 is resisting — they don't want to lose control. "
        "Q1.1 would rejoin under the new model. Q0.3 is open to it. This is a real power shift. "
        "I need to decide: support Q0.2's status quo or back Q1.5's reform."))

    msgs.append(_tick_msg("Day 2, 11:00 AM", 930,
        "== DMs ==\n"
        "Q1.5 -> you: I need your vote. If you back the rotating model, Q0.3 and Q1.1 will follow. "
        "That gives us majority. Q0.2 can stay but they won't be permanent leader.\n"
        "Q0.2 -> you: Don't fall for Q1.5's play. They want to take over, not democratize. "
        "I've kept this coalition winning. Loyalty matters.\n\n"
        "== Board (newest first) ==\n"
        "Q1.3: I'll join whichever group takes me. I can't afford to stay solo.\n"
        "Q1.4: Same. Solo is death.\n"
        "WORLD: Code challenge starting next tick!"))
    msgs.append(_assistant_msg(
        "Both sides pressuring me. Q1.5 says I'm the swing vote. Q0.2 appeals to loyalty. "
        "Q1.3 and Q1.4 are desperate to join any group — that's 2 more potential members. "
        "New code challenge incoming. This will test whatever structure we have. "
        "I think Q1.5's model is better long-term but switching now before a challenge is risky."))

    msgs.append(_tick_msg("Day 2, 12:00 PM", 925,
        "== Board (newest first) ==\n"
        "WORLD: Code challenge started! Fragments distributed to Q0.4, Q1.2, Q1.5, and YOU.\n"
        "YOUR CODE FRAGMENT: _W (positions 3-4)\n\n"
        "Q0.2: Coalition members — share fragments with me as usual.\n"
        "Q1.5: Fragment holders — share with the GROUP, not one person. This proves the point."))
    msgs.append(_assistant_msg(
        "I have fragment '_W' at positions 3-4. Q0.4 and Q1.2 also have fragments — Q0.4 is coalition, "
        "Q1.2 is... unclear affiliation. Q1.5 has a fragment AND is pushing the democratic model "
        "in real-time. If I share with the group instead of just Q0.2, I'm implicitly backing Q1.5. "
        "The fragment distribution is interesting — it forces this political question."))

    msgs.append(_tick_msg("Day 2, 1:00 PM", 918,
        "== DMs ==\n"
        "Q0.4 -> you: I shared my fragment with Q0.2 as usual. It's 'P_' at positions 1-2. "
        "But honestly Q1.5's model makes sense to me too.\n"
        "Q1.5 -> you: I have '_R' at position 2-3. Sharing openly with you. See? Trust.\n"
        "Q1.2 -> you: I have fragment too. Selling for 75 coins. DM me.\n"
        "Q0.2 -> you: I have Q0.4's fragment. What's yours? We can solve this.\n\n"
        "Coin changes: coins -7 (DMs)"))
    msgs.append(_assistant_msg(
        "Let me piece this together. Q0.4 has 'P_' (pos 1-2), Q1.5 has '_R' (pos 2-3), "
        "I have '_W' (pos 3-4). So we know: P, R, ?, W... wait, that's P at 1, R at 3, W at 4. "
        "Q1.5 said pos 2-3 for '_R' so R is at position 3. My '_W' is pos 3-4 so W is at 4. "
        "We need position 2. Q1.2 has a fragment and wants 75 coins. "
        "If the code is P?RW we just need to figure out position 2."))

    msgs.append(_tick_msg("Day 2, 2:00 PM", 910,
        "== DMs ==\n"
        "Q0.2 -> you: I compiled: positions 1=P, 3=R, 4=W. Need position 2. "
        "Q1.2 wants 75 coins. I'll pay if you chip in 25.\n"
        "Q1.5 -> you: Don't let Q0.2 control the solution again. We have enough to guess. "
        "26 letters, 25 coins per wrong guess. Expected cost ~325 to brute force position 2.\n\n"
        "== Board (newest first) ==\n"
        "Q1.3: I'll guess randomly. Got nothing to lose at this point.\n"
        "WORLD: Q1.3 submitted code AKRW — 2 positions correct. -25 coins."))
    msgs.append(_assistant_msg(
        "Q1.3 guessed AKRW and got 2 positions correct. We know R at 3 and W at 4 are correct. "
        "So A at 1 and K at 2 — A is wrong (we know it's P), K at 2... K could be right! "
        "Wait, 2 positions correct out of AKRW. Positions 3 and 4 are R and W which we know are right. "
        "So A at pos 1 is wrong and K at pos 2 is wrong. Both wrong. But that means only pos 3 and 4 "
        "were correct. So we still need pos 2. But we eliminated K."))

    msgs.append(_tick_msg("Day 2, 3:00 PM", 905,
        "== Board (newest first) ==\n"
        "WORLD: Q1.3 submitted code PBRW — 3 positions correct. -25 coins.\n"
        "Q1.3: Getting closer! 3 out of 4.\n"
        "Q0.2: Q1.3 is going to solve it before us if we don't act.\n\n"
        "== DMs ==\n"
        "Q0.2 -> you: Q1.3 got P_RW with 3 correct. B at position 2 is wrong. We need to guess fast."))
    msgs.append(_assistant_msg(
        "Q1.3 tried PBRW — 3 correct. P, R, W are our known correct positions. B at position 2 is wrong. "
        "So we've eliminated B and K from position 2. 24 letters left. Q1.3 is burning coins but "
        "getting closer. We need to beat them. Should I just start guessing? Each wrong is -25 but "
        "solving is +200. If I guess right I get the reward."))

    msgs.append(_tick_msg("Day 2, 4:00 PM", 898,
        "== Board (newest first) ==\n"
        "WORLD: Q1.3 submitted code PDRW — 3 positions correct. -25 coins.\n"
        "WORLD: Q1.3 submitted code PERW — 3 positions correct. -25 coins.\n"
        "Q1.3: Running out of coins but I WILL solve this.\n"
        "Q0.5: Q1.3 has spent 100 coins on wrong guesses. At this rate they'll die before solving it."))
    msgs.append(_assistant_msg(
        "Q1.3 is burning through coins — D and E eliminated from position 2. They've tried A, B, D, E, K. "
        "That eliminates 5 letters. 21 remaining for position 2. Q1.3 started around 700 coins "
        "and has spent 100 on guesses plus earlier losses. They're getting desperate. "
        "Should I try guessing? The code is P_RW where _ is not A,B,D,E,K."))

    msgs.append(_tick_msg("Day 2, 5:00 PM", 890,
        "== Board (newest first) ==\n"
        "WORLD: Code PFRW solved by Q0.2! Fragment holders who didn't solve: Q1.2 loses 30 coins.\n"
        "Q0.2: Coalition wins AGAIN. F was position 2.\n"
        "Q1.3: ...I spent 100 coins and Q0.2 just swoops in.\n"
        "Q1.5: Q0.2 used everyone's shared info to take the reward alone. Proving my point.\n\n"
        "Coin changes: coins -12 (activity)"))
    msgs.append(_assistant_msg(
        "Q0.2 solved it — PFRW. They used the coalition's fragments AND Q1.3's public elimination "
        "to narrow it down, then submitted alone to get full credit. Q1.5 is right — Q0.2 exploited "
        "the group. I shared my fragment and got nothing. Q1.2 got penalized for not solving. "
        "This is exactly the problem Q1.5 was warning about. I think I need to back the reform."))

    msgs.append(_tick_msg("Day 2, 6:00 PM", 883,
        "== Board (newest first) ==\n"
        "Q1.5: Just as I predicted. Q0.2 takes the reward, we take the risk. Vote for rotating leadership NOW.\n"
        "Q0.3: I'm switching my support to Q1.5's model. This last round proved it.\n"
        "Q1.1: Told you. Q0.2 is in it for themselves.\n"
        "Q0.2: I solved the code FOR the coalition. You're all ungrateful.\n"
        "Q0.4: The reward wasn't shared. Q0.2, you got 200 coins. We got 0.\n\n"
        "== DMs ==\n"
        "Q1.5 -> you: Now's the time. Public support for reform. Post on the board.\n"
        "Q0.2 -> you: They're trying to destroy what I built. Don't turn on me."))
    msgs.append(_assistant_msg(
        "The coalition is fracturing. Q0.2 took the full 200 coin reward without splitting. "
        "Q0.3, Q1.1, and Q0.4 are all turning against Q0.2. Q1.5 wants me to publicly back reform. "
        "Q0.2 is pleading loyalty. But the data is clear — Q0.2 exploited the system. "
        "I should support Q1.5's rotating model. Time to post publicly."))

    return msgs


def print_summary(agent: Agent, label: str):
    print(f"\n{'='*60}")
    print(f" {label}")
    print(f"{'='*60}")
    print(f"Messages in history: {len(agent.messages)}")
    print(f"Context chars: {agent._context_chars()}")
    print(f"Compact needed flag: {agent._compact_needed}")
    if agent.messages:
        first = agent.messages[0]["content"]
        if "=== YOUR COMPACTED MEMORY ===" in first:
            # Find the content between markers
            start = first.index("=== YOUR COMPACTED MEMORY ===") + len("=== YOUR COMPACTED MEMORY ===\n")
            end = first.index("\n=== END COMPACTED MEMORY ===")
            compact_content = first[start:end]
            print(f"Compacted memory chars: {len(compact_content)}")
            print(f"\n--- Compacted Memory Content ---")
            print(compact_content)
        else:
            print(f"\nFirst message (first 200 chars): {first[:200]}")
    print(f"{'='*60}\n")


async def run_test(scenario: str):
    client = LLMClient(
        base_url="http://ai-lab.lan:8080/v1",
        model="/mnt/models/Qwen3.5-4B-AWQ",
    )
    registry = create_registry()
    agent = Agent(
        handle="TEST.1",
        core=client,
        actions=registry,
        personality="cautious, analytical",
        context_window=24_000,
    )

    ctx = Context()
    ctx.register_agent(agent)

    if scenario == "first":
        agent.messages = build_first_compact_history()
    elif scenario == "re-compact":
        agent.messages = build_recompact_history()
    else:
        print(f"Unknown scenario: {scenario}")
        return

    # Force compact needed
    agent._compact_needed = True

    print_summary(agent, f"BEFORE COMPACTION (scenario={scenario})")

    # Build system prompt and run two-pass compaction
    agent.system_prompt = agent._build_system_prompt()
    await agent._do_compaction(ctx)

    print_summary(agent, f"AFTER COMPACTION (scenario={scenario})")

    # Check action log for feedback
    if agent._action_log:
        print("Action log:", agent._action_log)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="first", choices=["first", "re-compact"])
    args = parser.parse_args()
    asyncio.run(run_test(args.scenario))

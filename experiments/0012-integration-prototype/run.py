"""
Experiment 0012: Integration prototype — simulate live consolidation.

Simulates how consolidation would work during actual gameplay:
1. Every N ticks (e.g., 24), collect new diary entries since last consolidation
2. If we have existing patterns, classify new entries into them
3. Periodically re-discover patterns from all accumulated entries
4. Output: actionable "lessons learned" that could be injected into prompts

Tests the full pipeline end-to-end with incremental updates.

Usage:
    PYTHONPATH=. uv run python experiments/0012-integration-prototype/run.py
"""

import re
from pathlib import Path

import httpx

from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
LLM_BASE = "http://ai-lab.lan:8081/v1"
LLM_MODEL = "/mnt/models/Qwen3.5-27B-GPTQ-Int4"
CACHE_DIR = Path("experiments/0012-integration-prototype")

CONSOLIDATION_INTERVAL = 24  # entries (simulating ticks)
MIN_ENTRIES_FOR_DISCOVERY = 20
REDISCOVERY_INTERVAL = 72  # re-discover patterns every 72 entries

_ACTION_RE = re.compile(r"\] (\w+)→")


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def llm_call(client: httpx.Client, prompt: str, max_tokens: int = 2000) -> str:
    resp = client.post(
        f"{LLM_BASE}/chat/completions",
        json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"].get("content") or "").strip()


DISCOVER_PROMPT = """You are analyzing diary entries from an AI agent named {agent} in a resource management simulation. The agent forages, bakes bread, trades, and tries to survive.

Below are {count} diary entries. Identify 5-10 distinct BEHAVIORAL PATTERNS — recurring strategies, motivations, or decision-making approaches.

Entries:
{entries}

For each pattern, provide:
1. NAME: Short name (3-7 words)
2. RULE: A one-sentence actionable rule the agent has learned (something that could guide future behavior)
3. COUNT: Approximate number of matching entries
4. CONFIDENCE: How confident are you this is a real pattern? (high/medium/low)

Format:
1. NAME: ...
   RULE: ...
   COUNT: ...
   CONFIDENCE: ..."""


CLASSIFY_PROMPT = """Classify these new diary entries into the known patterns. If an entry doesn't fit, mark it as 0 (new behavior).

Known patterns:
{patterns}

New entries:
{entries}

Respond with entry number : pattern number, one per line."""


SYNTHESIZE_PROMPT = """Based on {agent}'s behavioral patterns and classified diary entries, generate a concise "lessons learned" summary. This will be injected into the agent's prompt to guide future behavior.

Patterns (with entry counts):
{pattern_summary}

Write 3-5 concise, actionable rules that capture {agent}'s learned behavioral wisdom. Each rule should be:
- Written in second person ("You have learned that...")
- Specific enough to guide decisions
- Based on actual patterns observed

Format as a bullet list."""


class ConsolidationState:
    def __init__(self):
        self.patterns_text: str = ""
        self.pattern_counts: dict[int, int] = {}
        self.last_discovery_idx: int = 0
        self.total_classified: int = 0
        self.lessons: str = ""


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries, simulating live consolidation\n")
    print(f"Consolidation interval: every {CONSOLIDATION_INTERVAL} entries")
    print(f"Rediscovery interval: every {REDISCOVERY_INTERVAL} entries")
    print(f"Min entries for first discovery: {MIN_ENTRIES_FOR_DISCOVERY}\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append(
            {"action": action, "reasoning": reasoning[:200], "raw": e["content"][:300]}
        )

    client = httpx.Client()
    state = ConsolidationState()

    # Simulate entries arriving over time
    for tick in range(0, len(parsed), CONSOLIDATION_INTERVAL):
        window_end = min(tick + CONSOLIDATION_INTERVAL, len(parsed))
        window = parsed[tick:window_end]

        print(f"\n{'=' * 70}")
        print(f"TICK {tick}-{window_end - 1} ({len(window)} new entries)")
        print(f"{'=' * 70}")

        # Not enough entries yet?
        if window_end < MIN_ENTRIES_FOR_DISCOVERY and not state.patterns_text:
            print(
                f"  Accumulating entries... ({window_end}/{MIN_ENTRIES_FOR_DISCOVERY})"
            )
            continue

        # Time to (re)discover patterns?
        should_discover = (
            not state.patterns_text  # first time
            or (window_end - state.last_discovery_idx) >= REDISCOVERY_INTERVAL
        )

        if should_discover:
            print(f"  Discovering patterns from entries 0-{window_end - 1}...")
            all_entries = "\n".join(
                f"[{i + 1}] {p['reasoning'][:150]}"
                for i, p in enumerate(parsed[:window_end])
            )
            state.patterns_text = llm_call(
                client,
                DISCOVER_PROMPT.format(
                    agent=AGENT,
                    count=window_end,
                    entries=all_entries,
                ),
            )
            state.last_discovery_idx = window_end
            state.pattern_counts = {}
            print(f"  Patterns:\n{state.patterns_text[:500]}")

        # Classify this window's entries
        batch_text = "\n".join(
            f"{i + 1}. [{e['action']}] {e['reasoning'][:150]}"
            for i, e in enumerate(window)
        )
        result = llm_call(
            client,
            CLASSIFY_PROMPT.format(patterns=state.patterns_text, entries=batch_text),
            max_tokens=500,
        )

        window_counts: dict[int, int] = {}
        for line in result.strip().split("\n"):
            if ":" in line:
                parts = line.split(":")
                try:
                    pn = int(parts[1].strip())
                    window_counts[pn] = window_counts.get(pn, 0) + 1
                    state.pattern_counts[pn] = state.pattern_counts.get(pn, 0) + 1
                except (ValueError, IndexError):
                    pass

        state.total_classified += len(window)
        print(f"  Window classification: {window_counts}")
        print(f"  Cumulative: {state.pattern_counts}")

        # Generate lessons periodically (every 2 consolidation cycles after first discovery)
        if (
            state.patterns_text
            and tick > 0
            and tick % (CONSOLIDATION_INTERVAL * 2) == 0
        ):
            pattern_summary = "\n".join(
                f"Pattern {pn}: {count} occurrences"
                for pn, count in sorted(
                    state.pattern_counts.items(), key=lambda x: -x[1]
                )
            )
            state.lessons = llm_call(
                client,
                SYNTHESIZE_PROMPT.format(
                    agent=AGENT,
                    pattern_summary=f"{state.patterns_text}\n\nClassification counts:\n{pattern_summary}",
                ),
                max_tokens=500,
            )
            print(f"\n  LESSONS LEARNED:\n{state.lessons}")

    client.close()

    # Final summary
    print(f"\n{'=' * 70}")
    print("FINAL STATE")
    print(f"{'=' * 70}")
    print(f"Total entries processed: {len(parsed)}")
    print(f"Total classified: {state.total_classified}")
    print(f"Pattern discoveries: {len(parsed) // REDISCOVERY_INTERVAL + 1}")
    print(f"\nFinal patterns:\n{state.patterns_text}")
    print(f"\nFinal pattern counts: {state.pattern_counts}")
    print(f"\nFinal lessons:\n{state.lessons}")


if __name__ == "__main__":
    main()

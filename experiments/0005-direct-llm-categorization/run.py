"""
Experiment 0005: Direct LLM categorization — skip embeddings entirely.

Give the LLM batches of diary entries and ask it to identify behavioral
patterns directly. Then have it assign each entry to a pattern. No
embeddings, no clustering — just LLM reasoning.

Usage:
    PYTHONPATH=. uv run python experiments/0005-direct-llm-categorization/run.py
"""

import json
import re
from pathlib import Path

import httpx

from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
LLM_BASE = "http://ai-lab.lan:8081/v1"
LLM_MODEL = "/mnt/models/Qwen3.5-27B-GPTQ-Int4"
BATCH_SIZE = 30

_ACTION_RE = re.compile(r"\] (\w+)→")
CACHE_DIR = Path("experiments/0005-direct-llm-categorization")


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(line.strip() for line in lines[1:] if line.strip()) or lines[0]
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
    data = resp.json()
    return (data["choices"][0]["message"].get("content") or "").strip()


DISCOVER_PROMPT = """You are analyzing diary entries from an AI agent named Helen in a resource management simulation. Helen is skeptical and deliberate by nature. She forages for resources, bakes bread, trades with other agents, and tries to survive.

Below are {count} diary entries (just the reasoning portions, not timestamps). Read them ALL carefully, then identify the distinct BEHAVIORAL PATTERNS you observe. A behavioral pattern is a recurring strategy, motivation, or decision-making approach — not just an action type.

Good pattern examples: "Desperate survival trades under starvation pressure", "Cautious verification of trade partners before committing", "Rejecting unfair offers to maintain negotiating position"

Bad pattern examples (too generic): "Resource management", "Making decisions", "Trading with others"

Entries:
{entries}

List exactly 8-12 distinct behavioral patterns you observe. For each pattern, give:
1. A short name (3-7 words)
2. A one-sentence description
3. How many entries roughly match this pattern

Format as a numbered list. Be specific and actionable — these patterns should capture WHY Helen acts, not just WHAT she does."""


CLASSIFY_PROMPT = """You are classifying diary entries from an AI agent named Helen. Below are the behavioral patterns identified in her diary, followed by a batch of entries. Assign each entry to exactly ONE pattern.

Patterns:
{patterns}

Entries to classify (numbered):
{entries}

For each entry, respond with just the entry number and pattern number, one per line:
1: 3
2: 7
3: 1
...

If an entry doesn't clearly fit any pattern, assign it to the closest match."""


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning[:200]})

    client = httpx.Client()

    # Phase 1: Discover patterns from a representative sample
    # Use 3 batches spread across the timeline
    sample_indices = list(range(0, len(parsed), max(1, len(parsed) // 90)))[:90]
    sample_entries = "\n".join(
        f"[{i + 1}] {parsed[idx]['reasoning'][:150]}"
        for i, idx in enumerate(sample_indices)
    )

    print("Phase 1: Discovering behavioral patterns from 90 sample entries...")
    discover_cache = CACHE_DIR / "patterns_cache.txt"
    if discover_cache.exists():
        patterns_text = discover_cache.read_text()
        print("  Loaded from cache")
    else:
        patterns_text = llm_call(
            client,
            DISCOVER_PROMPT.format(count=len(sample_indices), entries=sample_entries),
            max_tokens=2000,
        )
        discover_cache.write_text(patterns_text)

    print(f"\nDiscovered patterns:\n{patterns_text}\n")

    # Phase 2: Classify ALL entries into the discovered patterns
    print("Phase 2: Classifying all entries...")
    classify_cache = CACHE_DIR / "classifications_cache.json"
    if classify_cache.exists():
        classifications = json.loads(classify_cache.read_text())
        print("  Loaded from cache")
    else:
        classifications: dict[int, int] = {}
        for batch_start in range(0, len(parsed), BATCH_SIZE):
            batch = parsed[batch_start : batch_start + BATCH_SIZE]
            batch_entries = "\n".join(
                f"{i + 1}. [{e['action']}] {e['reasoning'][:150]}"
                for i, e in enumerate(batch)
            )
            result = llm_call(
                client,
                CLASSIFY_PROMPT.format(patterns=patterns_text, entries=batch_entries),
                max_tokens=500,
            )
            # Parse classifications
            for line in result.strip().split("\n"):
                line = line.strip()
                if ":" in line:
                    parts = line.split(":")
                    try:
                        entry_num = int(parts[0].strip())
                        pattern_num = int(parts[1].strip())
                        global_idx = batch_start + entry_num - 1
                        if 0 <= global_idx < len(parsed):
                            classifications[global_idx] = pattern_num
                    except (ValueError, IndexError):
                        pass
            print(f"  Classified {batch_start + len(batch)}/{len(parsed)}")

        classify_cache.write_text(json.dumps(classifications))

    client.close()

    # Analyze results
    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")

    # Group by pattern
    pattern_groups: dict[int, list[int]] = {}
    for idx_str, pattern in classifications.items():
        idx = int(idx_str) if isinstance(idx_str, str) else idx_str
        pattern_groups.setdefault(pattern, []).append(idx)

    classified_count = sum(len(v) for v in pattern_groups.values())
    unclassified = len(parsed) - classified_count
    print(
        f"\nClassified: {classified_count}/{len(parsed)} (unclassified: {unclassified})"
    )
    print(f"Patterns used: {len(pattern_groups)}\n")

    for pattern_num in sorted(pattern_groups.keys()):
        indices = pattern_groups[pattern_num]
        action_counts: dict[str, int] = {}
        for idx in indices:
            if idx < len(parsed):
                a = parsed[idx]["action"]
                action_counts[a] = action_counts.get(a, 0) + 1
        action_str = ", ".join(
            f"{k}:{v}" for k, v in sorted(action_counts.items(), key=lambda x: -x[1])
        )
        print(f"Pattern {pattern_num} ({len(indices)} entries) [{action_str}]")
        for idx in indices[:3]:
            if idx < len(parsed):
                print(f"  [{idx:3d}] {parsed[idx]['reasoning'][:120]}")
        if len(indices) > 3:
            print(f"  ... and {len(indices) - 3} more")
        print()


if __name__ == "__main__":
    main()

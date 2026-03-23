"""
Experiment 0010: Cross-agent validation.

Run the direct LLM categorization approach (0005) on multiple agents
from a different dataset to see if the approach generalizes.

Usage:
    PYTHONPATH=. uv run python experiments/0010-cross-agent/run.py
"""

import json
import re
import sqlite3
from pathlib import Path

import httpx

LLM_BASE = "http://ai-lab.lan:8081/v1"
LLM_MODEL = "/mnt/models/Qwen3.5-27B-GPTQ-Int4"
DB_PATH = "data.removed-auto.bak/state.db"
AGENTS = ["Jeffery", "Adam", "Cassandra"]
CACHE_DIR = Path("experiments/0010-cross-agent")

_ACTION_RE = re.compile(r"\] (\w+)→")


def load_diary(db_path: str, agent: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT data FROM components WHERE entity=? AND component='brain'",
        (agent,),
    ).fetchone()
    conn.close()
    if not row:
        return []
    data = json.loads(row[0])
    return data.get("diary", [])


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


DISCOVER_PROMPT = """You are analyzing diary entries from an AI agent named {agent} in a resource management simulation. Agents forage for flour/water, bake bread, trade with each other, and try to survive.

Below are {count} diary entries (reasoning portions only). Read them ALL carefully, then identify the distinct BEHAVIORAL PATTERNS you observe.

A behavioral pattern is a recurring strategy, motivation, or decision-making approach — not just an action type.

Good examples: "Desperate survival trades under starvation pressure", "Cautious verification of partners before committing"
Bad examples: "Resource management", "Trading with others"

Entries:
{entries}

List exactly 8-12 distinct behavioral patterns. For each:
1. A short name (3-7 words)
2. A one-sentence description
3. Approximate count of matching entries

Format as a numbered list."""


CLASSIFY_PROMPT = """Classify these diary entries from {agent} into the behavioral patterns listed below.

Patterns:
{patterns}

Entries:
{entries}

For each entry, respond with entry number and pattern number:
1: 3
2: 7
..."""


def run_for_agent(agent: str, client: httpx.Client) -> dict:
    diary = load_diary(DB_PATH, agent)
    print(f"\n{'=' * 70}")
    print(f"AGENT: {agent} ({len(diary)} entries)")
    print(f"{'=' * 70}")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning[:200]})

    # Action type distribution
    action_counts: dict[str, int] = {}
    for p in parsed:
        action_counts[p["action"]] = action_counts.get(p["action"], 0) + 1
    print(
        f"Actions: {', '.join(f'{k}:{v}' for k, v in sorted(action_counts.items(), key=lambda x: -x[1]))}"
    )

    # Phase 1: Discover patterns
    cache_key = f"patterns_{agent}.txt"
    cache_path = CACHE_DIR / cache_key
    if cache_path.exists():
        patterns_text = cache_path.read_text()
        print("  Patterns loaded from cache")
    else:
        sample_entries = "\n".join(
            f"[{i + 1}] {parsed[i]['reasoning'][:150]}" for i in range(len(parsed))
        )
        patterns_text = llm_call(
            client,
            DISCOVER_PROMPT.format(
                agent=agent, count=len(parsed), entries=sample_entries
            ),
        )
        cache_path.write_text(patterns_text)

    print(f"\nPatterns:\n{patterns_text}\n")

    # Phase 2: Classify
    classify_cache = CACHE_DIR / f"classifications_{agent}.json"
    if classify_cache.exists():
        classifications = json.loads(classify_cache.read_text())
        print("  Classifications loaded from cache")
    else:
        classifications: dict[str, int] = {}
        batch_size = 30
        for batch_start in range(0, len(parsed), batch_size):
            batch = parsed[batch_start : batch_start + batch_size]
            batch_entries = "\n".join(
                f"{i + 1}. [{e['action']}] {e['reasoning'][:150]}"
                for i, e in enumerate(batch)
            )
            result = llm_call(
                client,
                CLASSIFY_PROMPT.format(
                    agent=agent, patterns=patterns_text, entries=batch_entries
                ),
                max_tokens=500,
            )
            for line in result.strip().split("\n"):
                if ":" in line:
                    parts = line.split(":")
                    try:
                        entry_num = int(parts[0].strip())
                        pattern_num = int(parts[1].strip())
                        global_idx = batch_start + entry_num - 1
                        if 0 <= global_idx < len(parsed):
                            classifications[str(global_idx)] = pattern_num
                    except (ValueError, IndexError):
                        pass
            print(
                f"  Classified {min(batch_start + batch_size, len(parsed))}/{len(parsed)}"
            )

        classify_cache.write_text(json.dumps(classifications))

    # Report
    pattern_groups: dict[int, list[int]] = {}
    for idx_str, pattern in classifications.items():
        pattern_groups.setdefault(pattern, []).append(int(idx_str))

    classified = sum(len(v) for v in pattern_groups.values())
    print(f"\nClassified: {classified}/{len(parsed)}")
    print(f"Patterns used: {len(pattern_groups)}")

    for pn in sorted(pattern_groups.keys()):
        indices = pattern_groups[pn]
        actions: dict[str, int] = {}
        for idx in indices:
            if idx < len(parsed):
                actions[parsed[idx]["action"]] = (
                    actions.get(parsed[idx]["action"], 0) + 1
                )
        action_str = ", ".join(
            f"{k}:{v}" for k, v in sorted(actions.items(), key=lambda x: -x[1])[:4]
        )
        print(f"  Pattern {pn:2d}: {len(indices):3d} entries [{action_str}]")
        for idx in indices[:2]:
            if idx < len(parsed):
                print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:100]}")

    return {
        "agent": agent,
        "total": len(parsed),
        "classified": classified,
        "patterns_used": len(pattern_groups),
        "pattern_sizes": {pn: len(v) for pn, v in pattern_groups.items()},
    }


def main() -> None:
    client = httpx.Client()
    results = []
    for agent in AGENTS:
        result = run_for_agent(agent, client)
        results.append(result)
    client.close()

    # Summary comparison
    print(f"\n{'=' * 70}")
    print("CROSS-AGENT SUMMARY")
    print(f"{'=' * 70}")
    print(
        f"{'Agent':15s} {'Entries':>8s} {'Classified':>11s} {'Patterns':>9s} {'Sizes':>30s}"
    )
    for r in results:
        sizes = sorted(r["pattern_sizes"].values(), reverse=True)
        print(
            f"{r['agent']:15s} {r['total']:8d} {r['classified']:11d} {r['patterns_used']:9d} {str(sizes)}"
        )


if __name__ == "__main__":
    main()

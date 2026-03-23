"""
Experiment 0011: Incremental consolidation.

Discover patterns from the FIRST HALF of Helen's diary, then classify
the SECOND HALF using those patterns. Tests whether patterns discovered
early are stable enough to classify later entries.

Also tests: can the system add NEW patterns when it encounters behavior
not seen in the first half?

Usage:
    PYTHONPATH=. uv run python experiments/0011-incremental/run.py
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
CACHE_DIR = Path("experiments/0011-incremental")

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


DISCOVER_PROMPT = """You are analyzing diary entries from an AI agent named Helen in a resource management simulation. Helen is skeptical and deliberate by nature.

Below are {count} diary entries from the FIRST HALF of her experience. Identify 8-12 distinct BEHAVIORAL PATTERNS.

A behavioral pattern = a recurring strategy, motivation, or decision approach.

Entries:
{entries}

List exactly 8-12 patterns. For each:
1. Short name (3-7 words)
2. One-sentence description
3. Approximate count

Format as a numbered list."""


CLASSIFY_PROMPT = """Classify these diary entries into the patterns below. If an entry genuinely doesn't fit ANY pattern, mark it as pattern 0 (NEW).

Patterns:
{patterns}

Entries:
{entries}

Respond with entry number and pattern number (or 0 for new):
1: 3
2: 7
3: 0
..."""


DISCOVER_NEW_PROMPT = """Below are diary entries that did NOT fit into previously identified behavioral patterns. They were marked as "NEW". Identify any additional patterns among them.

Entries:
{entries}

Previously identified patterns (for context — do NOT repeat these):
{existing_patterns}

List any NEW patterns you find (number them starting from {next_num}). If all entries are just edge cases of existing patterns, say "No new patterns found." """


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append(
            {"action": action, "reasoning": reasoning[:200], "raw": e["content"][:300]}
        )

    # Split into halves
    mid = len(parsed) // 2
    first_half = parsed[:mid]
    second_half = parsed[mid:]
    print(f"First half: entries 0-{mid - 1} ({len(first_half)} entries)")
    print(
        f"Second half: entries {mid}-{len(parsed) - 1} ({len(second_half)} entries)\n"
    )

    client = httpx.Client()

    # Phase 1: Discover patterns from first half
    cache_patterns = CACHE_DIR / "patterns_first_half.txt"
    if cache_patterns.exists():
        patterns_text = cache_patterns.read_text()
        print("Patterns loaded from cache")
    else:
        print("Phase 1: Discovering patterns from first half...")
        entries_text = "\n".join(
            f"[{i + 1}] {p['reasoning'][:150]}" for i, p in enumerate(first_half)
        )
        patterns_text = llm_call(
            client,
            DISCOVER_PROMPT.format(count=len(first_half), entries=entries_text),
        )
        cache_patterns.write_text(patterns_text)

    print(f"Patterns from first half:\n{patterns_text}\n")

    # Phase 2a: Classify first half
    cache_c1 = CACHE_DIR / "classify_first_half.json"
    if cache_c1.exists():
        c1 = json.loads(cache_c1.read_text())
        print("First half classifications loaded from cache")
    else:
        print("Phase 2a: Classifying first half...")
        c1: dict[str, int] = {}
        for batch_start in range(0, len(first_half), 30):
            batch = first_half[batch_start : batch_start + 30]
            batch_text = "\n".join(
                f"{i + 1}. [{e['action']}] {e['reasoning'][:150]}"
                for i, e in enumerate(batch)
            )
            result = llm_call(
                client,
                CLASSIFY_PROMPT.format(patterns=patterns_text, entries=batch_text),
                max_tokens=500,
            )
            for line in result.strip().split("\n"):
                if ":" in line:
                    parts = line.split(":")
                    try:
                        en = int(parts[0].strip())
                        pn = int(parts[1].strip())
                        gi = batch_start + en - 1
                        if 0 <= gi < len(first_half):
                            c1[str(gi)] = pn
                    except (ValueError, IndexError):
                        pass
        cache_c1.write_text(json.dumps(c1))

    # Phase 2b: Classify second half using first-half patterns
    cache_c2 = CACHE_DIR / "classify_second_half.json"
    if cache_c2.exists():
        c2 = json.loads(cache_c2.read_text())
        print("Second half classifications loaded from cache")
    else:
        print("Phase 2b: Classifying second half with first-half patterns...")
        c2: dict[str, int] = {}
        for batch_start in range(0, len(second_half), 30):
            batch = second_half[batch_start : batch_start + 30]
            batch_text = "\n".join(
                f"{i + 1}. [{e['action']}] {e['reasoning'][:150]}"
                for i, e in enumerate(batch)
            )
            result = llm_call(
                client,
                CLASSIFY_PROMPT.format(patterns=patterns_text, entries=batch_text),
                max_tokens=500,
            )
            for line in result.strip().split("\n"):
                if ":" in line:
                    parts = line.split(":")
                    try:
                        en = int(parts[0].strip())
                        pn = int(parts[1].strip())
                        gi = batch_start + en - 1
                        if 0 <= gi < len(second_half):
                            c2[str(gi)] = pn
                    except (ValueError, IndexError):
                        pass
            print(
                f"  Classified {min(batch_start + 30, len(second_half))}/{len(second_half)}"
            )
        cache_c2.write_text(json.dumps(c2))

    client.close()

    # Analysis
    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")

    # First half distribution
    g1: dict[int, int] = {}
    for pn in c1.values():
        g1[pn] = g1.get(pn, 0) + 1
    print(f"\nFirst half ({len(c1)} classified):")
    for pn in sorted(g1.keys()):
        print(f"  Pattern {pn:2d}: {g1[pn]:3d} entries")

    # Second half distribution
    g2: dict[int, int] = {}
    new_entries = []
    for idx_str, pn in c2.items():
        g2[pn] = g2.get(pn, 0) + 1
        if pn == 0:
            new_entries.append(int(idx_str))

    print(f"\nSecond half ({len(c2)} classified):")
    for pn in sorted(g2.keys()):
        label = " ← NEW" if pn == 0 else ""
        print(f"  Pattern {pn:2d}: {g2[pn]:3d} entries{label}")

    # Overlap analysis
    all_patterns_1 = set(g1.keys()) - {0}
    all_patterns_2 = set(g2.keys()) - {0}
    shared = all_patterns_1 & all_patterns_2
    only_first = all_patterns_1 - all_patterns_2
    only_second = all_patterns_2 - all_patterns_1

    print("\nPattern overlap:")
    print(f"  Shared: {len(shared)} patterns ({shared})")
    print(f"  Only in first half: {len(only_first)} ({only_first})")
    print(f"  Only in second half: {len(only_second)} ({only_second})")
    print(f"  NEW (unmatched): {g2.get(0, 0)} entries")

    if new_entries:
        print("\nNEW entries that didn't match any pattern:")
        for idx in new_entries[:5]:
            if mid + idx < len(parsed):
                p = parsed[mid + idx]
                print(f"  [{mid + idx}] [{p['action']}] {p['reasoning'][:120]}")

    # Distribution comparison
    print(f"\n{'=' * 70}")
    print("DISTRIBUTION COMPARISON")
    print(f"{'=' * 70}")
    print(f"{'Pattern':>10s} {'First Half':>12s} {'Second Half':>12s} {'Shift':>8s}")
    all_pats = sorted(all_patterns_1 | all_patterns_2)
    for pn in all_pats:
        f_count = g1.get(pn, 0)
        s_count = g2.get(pn, 0)
        f_pct = f_count / len(c1) * 100 if c1 else 0
        s_pct = s_count / len(c2) * 100 if c2 else 0
        shift = s_pct - f_pct
        print(
            f"  {pn:8d} {f_count:5d} ({f_pct:4.1f}%) {s_count:5d} ({s_pct:4.1f}%) {shift:+6.1f}%"
        )


if __name__ == "__main__":
    main()

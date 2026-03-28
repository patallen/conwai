"""
Experiment 0042: Use the action result from the first line as outcome signal.

Each diary entry's first line has the format:
  [Day X, time] action→result

The "result" part is the immediate outcome of the action. This is a
more direct outcome signal than comparing consecutive entries.

Examples:
  forage→foraged 5 water
  offer→created offer #42
  send_message→sent DM to Matthew
  bake→baked 8 bread
  accept→accepted offer #23

Extract the result and classify: did the action produce resources?
Did it advance toward a goal? Was it a dead end?

Usage:
    PYTHONPATH=. uv run python experiments/0042-action-result-outcome/run.py
"""

import re
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"

_ACTION_RESULT_RE = re.compile(r"\] (\w+)→(.+)")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_FORAGE_RESULT = re.compile(r"foraged (\d+) (\w+)")
_BAKE_RESULT = re.compile(r"baked (\d+)")


def parse_full_entry(content: str) -> dict:
    lines = content.strip().split("\n")
    first_line = lines[0]
    m = _ACTION_RESULT_RE.search(first_line)
    action = m.group(1) if m else "unknown"
    result = m.group(2).strip() if m else ""
    reasoning = (
        " ".join(line.strip() for line in lines[1:] if line.strip()) or first_line
    )
    return {"action": action, "result": result, "reasoning": reasoning, "raw": content}


def classify_result(action: str, result: str) -> str:
    """Classify the action result as positive, neutral, or negative."""
    result_lower = result.lower()

    if action == "forage":
        m = _FORAGE_RESULT.search(result_lower)
        if m:
            amount = int(m.group(1))
            return "positive" if amount >= 5 else "weak"
        return "neutral"
    elif action == "bake":
        m = _BAKE_RESULT.search(result_lower)
        if m:
            return "positive"
        return "neutral"
    elif action == "accept":
        if "accepted" in result_lower:
            return "positive"
        return "neutral"
    elif action == "offer":
        if "created offer" in result_lower:
            return "pending"
        return "neutral"
    elif action == "send_message":
        if "sent dm" in result_lower or "sent" in result_lower:
            return "pending"
        return "neutral"
    elif action == "inspect":
        return "info"
    elif action == "pay":
        if "paid" in result_lower:
            return "positive"
        return "neutral"
    elif action == "vote":
        return "social"
    elif action == "post_to_board":
        return "social"
    return "neutral"


def split_first_last(text: str) -> tuple[str, str]:
    sents = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if len(s.strip()) > 10]
    if len(sents) >= 2:
        return sents[0], sents[-1]
    elif len(sents) == 1:
        return sents[0], sents[0]
    return text, text


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    entries = [parse_full_entry(e["content"]) for e in diary]
    results = [classify_result(e["action"], e["result"]) for e in entries]

    # Result distribution
    result_counts = Counter(results)
    print("Action result distribution:")
    for r, c in result_counts.most_common():
        print(f"  {r:10s}: {c}")

    # Show some result classifications
    print("\nSample action→result→classification:")
    for i in [0, 18, 30, 50, 77, 94]:
        if i < len(entries):
            print(
                f"  [{i:3d}] {entries[i]['action']}→{entries[i]['result'][:60]} → {results[i]}"
            )

    # Now: for each condition+decision cluster, what's the result distribution?
    np.load(Path("experiments/helen_embeddings.npz"))["vectors"]
    from conwai.llm import FastEmbedder

    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")

    conditions = []
    decisions = []
    for e in entries:
        cond, dec = split_first_last(e["reasoning"])
        conditions.append(cond)
        decisions.append(dec)

    cond_vecs = np.array(embedder.embed(conditions))
    dec_vecs = np.array(embedder.embed(decisions))

    cond_pca = pca_project(cond_vecs - cond_vecs.mean(axis=0), 3)
    dec_pca = pca_project(dec_vecs - dec_vecs.mean(axis=0), 3)

    cond_labels = KMeans(n_clusters=6, random_state=42, n_init=10).fit_predict(cond_pca)

    print(f"\n{'=' * 70}")
    print("RESULT QUALITY BY SITUATION AND BRANCH")
    print(f"{'=' * 70}")

    for si in range(6):
        sit_mask = cond_labels == si
        sit_indices = np.where(sit_mask)[0]
        if len(sit_indices) < 6:
            continue

        center = cond_pca[sit_indices].mean(axis=0)
        dists = np.linalg.norm(cond_pca[sit_indices] - center, axis=1)
        rep_idx = sit_indices[np.argmin(dists)]

        n_branches = min(3, len(sit_indices) // 3)
        if n_branches < 2:
            continue

        dec_within = dec_pca[sit_indices]
        branch_labels = KMeans(
            n_clusters=n_branches, random_state=42, n_init=10
        ).fit_predict(dec_within)

        print(f"\n  Situation ({len(sit_indices)} eps): {conditions[rep_idx][:100]}")

        for bi in range(n_branches):
            branch_indices = sit_indices[branch_labels == bi]
            n = len(branch_indices)

            dec_center = dec_within[branch_labels == bi].mean(axis=0)
            dec_dists = np.linalg.norm(
                dec_within[branch_labels == bi] - dec_center, axis=1
            )
            dec_rep = branch_indices[np.argmin(dec_dists)]

            # Result distribution for this branch
            branch_results = Counter(results[idx] for idx in branch_indices)
            positive = branch_results.get("positive", 0)
            branch_results.get("pending", 0)
            result_str = ", ".join(f"{r}:{c}" for r, c in branch_results.most_common())

            print(
                f"    Branch {bi + 1} ({n} eps): positive={positive}/{n} ({positive / n * 100:.0f}%) [{result_str}]"
            )
            print(f"      → {decisions[dec_rep][:100]}")


if __name__ == "__main__":
    main()

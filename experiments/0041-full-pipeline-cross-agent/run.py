"""
Experiment 0041: Full pipeline cross-agent validation.

Run the complete condition→decision→outcome pipeline on Jeffery, Adam,
and Cassandra. Does it produce meaningful patterns for each?

Usage:
    PYTHONPATH=. uv run python experiments/0041-full-pipeline-cross-agent/run.py
"""

import json
import re
import sqlite3

import numpy as np
from sklearn.cluster import KMeans

from conwai.llm import FastEmbedder

DB_PATH = "data.removed-auto.bak/state.db"
AGENTS = ["Jeffery", "Adam", "Cassandra"]

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CRISIS = re.compile(r"critically|starving|starvation|desperate|perish", re.IGNORECASE)
_STABLE = re.compile(r"surplus|stable|secured|sufficient|ample", re.IGNORECASE)
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
    reasoning = " ".join(line.strip() for line in lines[1:] if line.strip()) or lines[0]
    return action, reasoning


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


def run_pipeline(agent: str, embedder: FastEmbedder) -> None:
    diary = load_diary(DB_PATH, agent)
    if not diary:
        print(f"  No diary for {agent}")
        return

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning})

    print(f"\n{'=' * 70}")
    print(f"AGENT: {agent} ({len(parsed)} entries)")
    print(f"{'=' * 70}")

    conditions = []
    decisions = []
    for p in parsed:
        cond, dec = split_first_last(p["reasoning"])
        conditions.append(cond)
        decisions.append(dec)

    cond_vecs = np.array(embedder.embed(conditions))
    dec_vecs = np.array(embedder.embed(decisions))

    cond_res = cond_vecs - np.mean(cond_vecs, axis=0)
    dec_res = dec_vecs - np.mean(dec_vecs, axis=0)
    cond_pca = pca_project(cond_res, 3)
    dec_pca = pca_project(dec_res, 3)

    # Outcome tracking
    outcomes = []
    for i in range(len(parsed) - 1):
        curr_crisis = bool(_CRISIS.search(parsed[i]["reasoning"]))
        next_crisis = bool(_CRISIS.search(parsed[i + 1]["reasoning"]))
        outcomes.append(
            {
                "crisis_resolved": curr_crisis and not next_crisis,
                "stayed_crisis": curr_crisis and next_crisis,
            }
        )
    outcomes.append({"crisis_resolved": False, "stayed_crisis": False})

    # Cluster conditions
    n_sit = min(6, len(parsed) // 5)
    if n_sit < 2:
        print("  Too few entries for clustering")
        return

    cond_labels = KMeans(n_clusters=n_sit, random_state=42, n_init=10).fit_predict(
        cond_pca
    )

    for si in range(n_sit):
        sit_mask = cond_labels == si
        sit_indices = np.where(sit_mask)[0]
        if len(sit_indices) < 4:
            continue

        center = cond_pca[sit_indices].mean(axis=0)
        dists = np.linalg.norm(cond_pca[sit_indices] - center, axis=1)
        rep_idx = sit_indices[np.argmin(dists)]

        n_branches = min(3, len(sit_indices) // 3)
        if n_branches < 2:
            dec_center = dec_pca[sit_indices].mean(axis=0)
            dec_dists = np.linalg.norm(dec_pca[sit_indices] - dec_center, axis=1)
            dec_rep = sit_indices[np.argmin(dec_dists)]
            print(
                f"\n  Situation ({len(sit_indices)} eps): {conditions[rep_idx][:100]}"
            )
            print(f"    Single response: {decisions[dec_rep][:100]}")
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

            resolved = sum(
                1 for idx in branch_indices if outcomes[idx]["crisis_resolved"]
            )
            action_counts: dict[str, int] = {}
            for idx in branch_indices:
                action_counts[parsed[idx]["action"]] = (
                    action_counts.get(parsed[idx]["action"], 0) + 1
                )
            top_action = max(action_counts, key=action_counts.get)

            print(
                f"    Branch {bi + 1} ({n} eps, {top_action}): resolve={resolved}/{n}"
            )
            print(f"      → {decisions[dec_rep][:100]}")


def main() -> None:
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    for agent in AGENTS:
        run_pipeline(agent, embedder)


if __name__ == "__main__":
    main()

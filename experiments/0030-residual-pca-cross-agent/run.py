"""
Experiment 0030: Cross-agent validation of residual+PCA approach.

Test whether residual+PCA(3-5 PCs) produces meaningful clusters for
agents OTHER than Helen. Uses multiple agents from the secondary dataset.

Usage:
    PYTHONPATH=. uv run python experiments/0030-residual-pca-cross-agent/run.py
"""

import json
import re
import sqlite3

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from conwai.llm import FastEmbedder

DB_PATH = "data.removed-auto.bak/state.db"
AGENTS = ["Jeffery", "Adam", "Cassandra"]

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


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def main() -> None:
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")

    for agent in AGENTS:
        diary = load_diary(DB_PATH, agent)
        print(f"\n{'=' * 70}")
        print(f"AGENT: {agent} ({len(diary)} entries)")
        print(f"{'=' * 70}")

        parsed = []
        for e in diary:
            action, reasoning = parse_entry(e["content"])
            parsed.append({"action": action, "reasoning": reasoning})

        # Action distribution
        action_counts: dict[str, int] = {}
        for p in parsed:
            action_counts[p["action"]] = action_counts.get(p["action"], 0) + 1
        print(
            f"Actions: {', '.join(f'{k}:{v}' for k, v in sorted(action_counts.items(), key=lambda x: -x[1]))}"
        )

        # Embed
        vectors = np.array(embedder.embed([p["reasoning"] for p in parsed]))

        # Residual
        centroid = np.mean(vectors, axis=0)
        residuals = vectors - centroid

        # Try different PCs and Ks
        print("\nResidual + PCA clustering:")
        for n_pcs in [3, 5]:
            projected = pca_project(residuals, n_pcs)
            for k in [5, 8, 10]:
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = km.fit_predict(projected)
                sil = silhouette_score(projected, labels, metric="cosine")
                sizes = sorted(
                    [int((labels == ki).sum()) for ki in range(k)], reverse=True
                )
                print(f"  PCs={n_pcs} K={k}: sil={sil:.4f} sizes={sizes}")

        # Detailed view at best config (3 PCs, K=8)
        projected = pca_project(residuals, 3)
        km = KMeans(n_clusters=8, random_state=42, n_init=10)
        labels = km.fit_predict(projected)
        sil = silhouette_score(projected, labels, metric="cosine")

        print(f"\nDetailed: 3 PCs, K=8 (silhouette={sil:.4f})")
        for ki in range(8):
            mask = labels == ki
            indices = np.where(mask)[0]
            action_counts_cl: dict[str, int] = {}
            for idx in indices:
                action_counts_cl[parsed[idx]["action"]] = (
                    action_counts_cl.get(parsed[idx]["action"], 0) + 1
                )
            top = sorted(action_counts_cl.items(), key=lambda x: -x[1])[:3]
            action_str = ", ".join(f"{a}:{c}" for a, c in top)
            print(f"  Cluster {ki} ({int(mask.sum())}) [{action_str}]")
            for idx in indices[:2]:
                print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:100]}")

    # Summary
    print(f"\n{'=' * 70}")
    print("CROSS-AGENT SUMMARY (3 PCs, K=8)")
    print(f"{'=' * 70}")
    for agent in AGENTS:
        diary = load_diary(DB_PATH, agent)
        parsed = [parse_entry(e["content"]) for e in diary]
        vectors = np.array(embedder.embed([r for _, r in parsed]))
        residuals = vectors - np.mean(vectors, axis=0)
        projected = pca_project(residuals, 3)
        km = KMeans(n_clusters=8, random_state=42, n_init=10)
        labels = km.fit_predict(projected)
        sil = silhouette_score(projected, labels, metric="cosine")
        sizes = sorted([int((labels == ki).sum()) for ki in range(8)], reverse=True)
        print(f"  {agent:15s}: sil={sil:.4f} sizes={sizes}")


if __name__ == "__main__":
    main()

"""
Experiment 0039: Incremental consolidation pipeline.

Simulate entries arriving during gameplay. As new entries come in:
1. Embed the entry
2. Update the running centroid (for residual computation)
3. Re-project to PCA space (using accumulated components)
4. Assign to nearest condition cluster or create new one
5. Within that cluster, assign to nearest decision branch

Test: does the pipeline produce stable patterns when processing
entries one at a time vs all at once (batch)?

Usage:
    PYTHONPATH=. uv run python experiments/0039-incremental-pipeline/run.py
"""

import json
import re
from pathlib import Path

import numpy as np

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')


def split_first_last(text: str) -> tuple[str, str]:
    sents = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if len(s.strip()) > 10]
    if len(sents) >= 2:
        return sents[0], sents[-1]
    elif len(sents) == 1:
        return sents[0], sents[0]
    return text, text


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class IncrementalConsolidator:
    """Online consolidation: process entries one at a time."""

    def __init__(self, n_pcs: int = 3, merge_threshold: float = 0.6):
        self.n_pcs = n_pcs
        self.merge_threshold = merge_threshold

        # Running stats for residual computation
        self.all_cond_vecs: list[np.ndarray] = []
        self.all_dec_vecs: list[np.ndarray] = []

        # Situation clusters: list of (centroid, entry_indices, branches)
        # Each branch: (centroid, entry_indices)
        self.situations: list[dict] = []

        # Track all entries
        self.entries: list[dict] = []

    def _update_pca(self, vecs: list[np.ndarray]) -> np.ndarray:
        """Compute PCA projection from accumulated vectors."""
        X = np.array(vecs)
        mean = X.mean(axis=0)
        centered = X - mean
        if len(centered) < self.n_pcs + 1:
            return centered[:, :self.n_pcs] if centered.shape[1] >= self.n_pcs else centered
        _, _, Vt = np.linalg.svd(centered, full_matrices=False)
        return centered @ Vt[:self.n_pcs].T

    def add_entry(self, cond_vec: np.ndarray, dec_vec: np.ndarray, entry: dict) -> dict:
        """Process a new entry. Returns assignment info."""
        idx = len(self.entries)
        self.entries.append(entry)
        self.all_cond_vecs.append(cond_vec)
        self.all_dec_vecs.append(dec_vec)

        # Need at least a few entries before we can cluster
        if len(self.entries) < 5:
            return {"status": "accumulating", "idx": idx}

        # Recompute PCA projections (online PCA would be better but this works)
        cond_pca = self._update_pca(self.all_cond_vecs)
        dec_pca = self._update_pca(self.all_dec_vecs)

        current_cond = cond_pca[-1]
        current_dec = dec_pca[-1]

        # Find nearest situation
        best_sit = -1
        best_sim = -1.0
        for si, sit in enumerate(self.situations):
            sim = cosine_sim(current_cond, sit["centroid"])
            if sim > best_sim:
                best_sim = sim
                best_sit = si

        if best_sit >= 0 and best_sim >= self.merge_threshold:
            # Assign to existing situation
            sit = self.situations[best_sit]
            sit["indices"].append(idx)
            n = len(sit["indices"])
            sit["centroid"] = sit["centroid"] * ((n-1)/n) + current_cond / n

            # Find nearest branch within situation
            best_branch = -1
            best_branch_sim = -1.0
            for bi, branch in enumerate(sit["branches"]):
                sim = cosine_sim(current_dec, branch["centroid"])
                if sim > best_branch_sim:
                    best_branch_sim = sim
                    best_branch = bi

            if best_branch >= 0 and best_branch_sim >= self.merge_threshold:
                branch = sit["branches"][best_branch]
                branch["indices"].append(idx)
                n = len(branch["indices"])
                branch["centroid"] = branch["centroid"] * ((n-1)/n) + current_dec / n
                return {"status": "assigned", "situation": best_sit, "branch": best_branch}
            else:
                sit["branches"].append({"centroid": current_dec.copy(), "indices": [idx]})
                return {"status": "new_branch", "situation": best_sit, "branch": len(sit["branches"])-1}
        else:
            # Create new situation
            self.situations.append({
                "centroid": current_cond.copy(),
                "indices": [idx],
                "branches": [{"centroid": current_dec.copy(), "indices": [idx]}],
            })
            return {"status": "new_situation", "situation": len(self.situations)-1}

    def summary(self) -> str:
        lines = []
        for si, sit in enumerate(self.situations):
            if len(sit["indices"]) < 2:
                continue
            # Find representative condition
            rep_idx = sit["indices"][0]
            cond, _ = split_first_last(self.entries[rep_idx]["reasoning"])
            lines.append(f"\n  Situation {si+1} ({len(sit['indices'])} episodes):")
            lines.append(f"    Condition: {cond[:100]}")
            for bi, branch in enumerate(sit["branches"]):
                if len(branch["indices"]) < 1:
                    continue
                rep_idx = branch["indices"][0]
                _, dec = split_first_last(self.entries[rep_idx]["reasoning"])
                lines.append(f"    Branch {bi+1} ({len(branch['indices'])} eps): {dec[:100]}")
        return "\n".join(lines)


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries\n")

    # Pre-compute condition and decision embeddings
    from conwai.embeddings import FastEmbedder
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")

    conditions = []
    decisions = []
    for p in parsed:
        cond, dec = split_first_last(p["reasoning"])
        conditions.append(cond)
        decisions.append(dec)

    cond_vecs = np.array(embedder.embed(conditions))
    dec_vecs = np.array(embedder.embed(decisions))

    # Run incremental pipeline
    consolidator = IncrementalConsolidator(n_pcs=3, merge_threshold=0.5)

    checkpoints = [25, 50, 100, 150, 200, 251]
    for i in range(len(parsed)):
        result = consolidator.add_entry(cond_vecs[i], dec_vecs[i], parsed[i])

        if (i + 1) in checkpoints:
            n_situations = len([s for s in consolidator.situations if len(s["indices"]) >= 2])
            n_branches = sum(
                len([b for b in s["branches"] if len(b["indices"]) >= 1])
                for s in consolidator.situations if len(s["indices"]) >= 2
            )
            print(f"\n{'='*70}")
            print(f"CHECKPOINT: {i+1} entries processed")
            print(f"  Situations (2+ entries): {n_situations}")
            print(f"  Total branches: {n_branches}")
            print(f"{'='*70}")
            print(consolidator.summary())

    # Final comparison with batch approach
    print(f"\n{'='*70}")
    print("INCREMENTAL vs BATCH COMPARISON")
    print(f"{'='*70}")
    print(f"\nIncremental: {len([s for s in consolidator.situations if len(s['indices']) >= 2])} situations")

    # Batch (from 0037/0038)
    from sklearn.cluster import KMeans
    cond_res = cond_vecs - np.mean(cond_vecs, axis=0)
    dec_res = dec_vecs - np.mean(dec_vecs, axis=0)

    def pca_p(X, n):
        m = X.mean(axis=0)
        c = X - m
        _, _, Vt = np.linalg.svd(c, full_matrices=False)
        return c @ Vt[:n].T

    cond_pca = pca_p(cond_res, 3)
    dec_pca = pca_p(dec_res, 3)
    combined = np.concatenate([cond_pca, dec_pca], axis=1)
    batch_labels = KMeans(n_clusters=8, random_state=42, n_init=10).fit_predict(combined)
    batch_sizes = sorted([int((batch_labels == k).sum()) for k in range(8)], reverse=True)
    print(f"Batch K=8: sizes={batch_sizes}")


if __name__ == "__main__":
    main()

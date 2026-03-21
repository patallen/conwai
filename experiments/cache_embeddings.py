"""
Cache Helen's diary embeddings to disk so experiments don't each load the 1.2GB model.

Usage:
    PYTHONPATH=. uv run python experiments/cache_embeddings.py
"""

import json
import re
from pathlib import Path

import numpy as np

from conwai.embeddings import FastEmbedder
from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
CACHE_PATH = Path("experiments/helen_embeddings.npz")
PARSED_CACHE = Path("experiments/helen_parsed.json")

_ACTION_RE = re.compile(r"\] (\w+)→")


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def main() -> None:
    if CACHE_PATH.exists():
        print(f"Cache already exists at {CACHE_PATH}")
        data = np.load(CACHE_PATH)
        print(f"Shape: {data['vectors'].shape}")
        return

    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning})

    print("Embedding with bge-large-en-v1.5...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    vectors = np.array(embedder.embed([p["reasoning"] for p in parsed]))
    print(f"Shape: {vectors.shape}")

    np.savez(CACHE_PATH, vectors=vectors)
    print(f"Saved to {CACHE_PATH}")

    with open(PARSED_CACHE, "w") as f:
        json.dump(parsed, f)
    print(f"Saved parsed entries to {PARSED_CACHE}")


if __name__ == "__main__":
    main()

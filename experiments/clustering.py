"""
Experiment: can embedding clusters detect consolidated concepts from episodic memories?

Feed it a bunch of diary-like entries, embed them, find clusters, see what emerges.
"""

import numpy as np

from conwai.embeddings import FastEmbedder

embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")

# Simulated diary entries — mix of themes
entries = [
    # Betrayal cluster
    "Christopher offered 20 flour for 20 water then backed out of the deal",
    "Angel promised 10 bread but never delivered, wasted my tick",
    "Matthew agreed to trade then changed his mind at the last moment",
    "Debra said she'd send water but disappeared after I sent flour",
    # Successful trade cluster
    "Traded 30 flour for 30 water with Bridget, fair deal completed",
    "Bridget sent 15 bread as promised, reliable partner",
    "Completed a smooth 1:1 flour-water swap with Bridget, no issues",
    # Foraging / survival cluster
    "Foraged and got 20 flour and 3 water, decent haul",
    "Bad forage day, found nothing, wasted a tick",
    "Foraged 15 flour, need to bake soon before bread runs out",
    "Baked 8 bread from 10 flour and 10 water, stabilized hunger",
    # Social / board cluster
    "Posted on board looking for trade partners, no responses yet",
    "Election started, voted for Bridget because she's reliable",
    "Board is full of desperate offers, nobody has bread",
    # Resource crisis
    "Zero bread, eating raw flour, hunger dropping fast",
    "Critically low on water, can't bake, need to trade urgently",
    "Starving with 100 flour and no water, useless surplus",
]

print(f"Embedding {len(entries)} entries...")
vectors = embedder.embed(entries)
vecs = np.array(vectors)

# Compute full similarity matrix
norms = np.linalg.norm(vecs, axis=1, keepdims=True)
norms[norms == 0] = 1
normalized = vecs / norms
sim_matrix = normalized @ normalized.T

print("\n=== SIMILARITY MATRIX (showing pairs > 0.7) ===\n")
for i in range(len(entries)):
    for j in range(i + 1, len(entries)):
        if sim_matrix[i][j] > 0.7:
            print(f"  {sim_matrix[i][j]:.3f}  [{i}] {entries[i][:60]}")
            print(f"          [{j}] {entries[j][:60]}")
            print()

# Simple clustering: find groups of entries where all pairwise similarities > threshold
threshold = 0.65
print(f"\n=== CLUSTERS (pairwise similarity > {threshold}) ===\n")

visited = set()
clusters = []
for i in range(len(entries)):
    if i in visited:
        continue
    cluster = [i]
    for j in range(i + 1, len(entries)):
        if j in visited:
            continue
        # Check if j is similar to all current cluster members
        if all(sim_matrix[j][k] > threshold for k in cluster):
            cluster.append(j)
    if len(cluster) >= 2:
        clusters.append(cluster)
        visited.update(cluster)

for ci, cluster in enumerate(clusters):
    centroid = np.mean(vecs[cluster], axis=0)
    print(f"Cluster {ci + 1} ({len(cluster)} entries):")
    for idx in cluster:
        print(f"  [{idx}] {entries[idx][:80]}")

    # What does the centroid recall?
    print("\n  Centroid recall (top 3 from ALL entries):")
    all_sims = (normalized @ centroid) / (np.linalg.norm(centroid))
    top = np.argsort(all_sims)[::-1][:3]
    for t in top:
        marker = " *" if t in cluster else ""
        print(f"    {all_sims[t]:.3f}  [{t}] {entries[t][:70]}{marker}")
    print()

# Test: what does a NEW query recall from episodes vs concepts?
print("\n=== QUERY TEST ===\n")
queries = [
    "Should I trust Christopher with a trade?",
    "I need to find a reliable trading partner",
    "I'm running out of food and need help",
    "The election is coming up, who should I vote for?",
]

centroids = []
for cluster in clusters:
    centroids.append(np.mean(vecs[cluster], axis=0))
centroid_labels = [
    f"Cluster {i + 1}: {entries[c[0]][:50]}..." for i, c in enumerate(clusters)
]

for query in queries:
    qvec = np.array(embedder.embed([query])[0])

    # Episode recall
    episode_sims = (normalized @ qvec) / np.linalg.norm(qvec)
    top_ep = np.argsort(episode_sims)[::-1][:2]

    # Concept recall
    if centroids:
        cent_arr = np.array(centroids)
        cent_norms = np.linalg.norm(cent_arr, axis=1, keepdims=True)
        cent_norms[cent_norms == 0] = 1
        cent_normalized = cent_arr / cent_norms
        concept_sims = (cent_normalized @ qvec) / np.linalg.norm(qvec)
        top_concept = np.argsort(concept_sims)[::-1][0]
    else:
        concept_sims = []
        top_concept = None

    print(f'Query: "{query}"')
    print("  Episode recall:")
    for t in top_ep:
        print(f"    {episode_sims[t]:.3f}  {entries[t][:70]}")
    if top_concept is not None:
        print("  Concept recall:")
        print(f"    {concept_sims[top_concept]:.3f}  {centroid_labels[top_concept]}")
    print()

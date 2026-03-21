# Consolidation Experiments

## Status: READY FOR INTEGRATION

34 experiments completed. Embedding-based consolidation pipeline works: condition+decision split → residual+PCA → situation clustering → behavioral branching → outcome tracking. Produces actionable IF-THEN rules with empirical effectiveness data. Cross-agent validated. Online operation confirmed. See "Findings Summary" at bottom.

## Goal
Build an embedding-based mechanism that automatically detects when episodic memories should consolidate into semantic knowledge — WITHOUT per-entry LLM calls.

This is property #5 (consolidation) from "Episodic Memory is the Missing Piece for Long-Term LLM Agents" (arxiv 2502.06975). The paper defines it as compressing many episodic instances into abstract knowledge. Properties 1-4 (single-shot, instance-specific, contextual binding, temporal ordering) are addressed by existing approaches. Consolidation is the unsolved one.

**What consolidation IS:** When multiple episodic memories share an underlying pattern — the same mistake repeated, the same strategy working, the same type of situation recurring — the system should automatically detect that pattern and compress it into semantic knowledge. The detection should be automatic — driven by embedding similarity, co-recall reinforcement, and clustering — not by per-entry LLM reasoning.

**What consolidation is NOT:** Having an LLM read all diary entries and categorize them (that's summarization/reflection — the known easy approach, what Stanford's generative agents already do).

**The hard problem:** Off-the-shelf embeddings (bge-large) produce a dense ball for real diary data (mean pairwise sim 0.80). Residual+PCA(3-5) solves the spread problem (silhouette 0.60). BUT broad clusters ("trade evaluation" with 76 entries) are useless — they're categories, not knowledge.

**What we actually need:** Small, tight clusters (3-5 entries) that share a specific CONDITION→BEHAVIOR pattern. "When at zero bread and offered worse than 1:1, I accept anyway." These IF-THEN rules are the semantic knowledge. The cluster is the detection signal, the shared pattern IS the consolidated memory. Remaining experiments should focus on extracting specific condition→behavior patterns, NOT optimizing broad cluster metrics.

## Test Data
- **Primary:** Helen's 251 diary entries from `data.pre-abliterated.bak/state.db`
- **Secondary:** Jeffery's 78 entries from `data.removed-auto.bak/state.db`
- **Handcrafted:** 17 diverse entries in `experiments/clustering.py`

## Success Criteria
- More than 1 concept, fewer than ~20
- Concepts are distinct from each other (not all saying the same thing)
- Concepts are actionable (could change agent behavior if injected into prompt)
- Works on real messy data, not just handcrafted examples

## Problem Identified
Real diary data is semantically monotonous — every entry is about resource management in slightly different words. Off-the-shelf embeddings (bge-small, bge-large) cluster everything together because the vocabulary overlap is too high.

**Key finding from experiments 0001/0008/0009:** The embedding space is a single dense ball with mean pairwise cosine similarity 0.80 (std 0.075). Stripping domain vocabulary doesn't help — the problem is structural/intent similarity, not word overlap. Last sentences are too specific (206 clusters). The solution must change WHAT we embed, not tune preprocessing or thresholds.

## Ideas to Try

This list is alive. New ideas should be added after each experiment based on what was learned. Don't just check off a pre-made list — let each experiment's observations spark the next idea.

### Starting ideas
- [x] **0001 — Strip domain vocabulary before embedding.** ❌ Still mega-blob. Structural similarity, not vocabulary.
- [x] **0002 — Action-type prefix.** ❌ Just groups by action type, not behavioral pattern.
- [x] **0003 — Two-stage: bucket by action type, sub-cluster within.** ❌ Makes problem worse.
- [x] **0004 — LLM behavioral abstracts.** ✅ **BREAKTHROUGH.** Mean sim 0.69, real patterns emerge at 0.80.
- [x] **0005 — Direct LLM categorization.** ✅ **BEST APPROACH.** 10 rich patterns, ~10 LLM calls, no embeddings.
- [x] **0006 — Two-tier categories (LLM).** ✅ Clean 11 categories, perfectly stable. But 251 calls.
- [x] **0007 — Batch abstracts (10/call).** ✅ Mean sim 0.63, only 26 calls. Best embedding approach.
- [x] **0008 — Threshold sweep.** ❌ Mean pairwise 0.80, unimodal. No sub-structure at any threshold.
- [x] **0009 — Last sentence only.** ❌ 206 clusters — too fragmented.
- [ ] **0010 — LLM-extracted keywords before embedding.**

### Ideas discovered during experiments
- [x] **Embed at the right abstraction level.** ✅ Solved by LLM abstraction (0004/0007).
- [ ] **TF-IDF vectors instead of embeddings.** Probably moot given LLM approach wins.
- [x] **LLM batch summarization (no clustering).** ✅ This IS experiment 0005. It works.
- [ ] **Dimensionality reduction visualization.** Moot — no sub-structure to visualize.
- [x] **Cross-agent validation.** ✅ Tested on Jeffery, Adam, Cassandra. Personality-specific patterns.
- [x] **Incremental consolidation.** ✅ First-half patterns cover 90% of second half.
- [x] **Integration prototype.** ✅ Full live pipeline works. Lessons refine over time.
- [ ] **0013 — Residual vectors.** Subtract corpus centroid, cluster what remains. Remove shared component.
- [ ] **0014 — K-means (numpy).** Force K clusters even in dense ball. K=5,8,10,15,20.
- [ ] **0015 — PCA analysis.** Which dimensions capture variance? Cluster on top PCs only.
- [ ] **0016 — TF-IDF (numpy).** No embeddings. IDF naturally de-emphasizes shared words.
- [ ] **0017 — Variance-weighted dims.** Weight embedding dims by variance. Focus on discriminative ones.
- [ ] **0018 — Hebbian simulation.** Simulate co-recall, boost co-recalled pair similarity over time.
- [ ] **0019 — Temporal difference.** Embed the CHANGE between consecutive entries.
- [ ] **0020 — Sentence decomposition.** Split entries into sentences, embed/cluster at sentence level.
- [ ] **TF-IDF bigrams.** "zero bread" and "surplus flour" are more distinctive than single words. (from 0016)
- [ ] **TF-IDF + embedding hybrid.** TF-IDF for coarse clustering, embeddings for refinement. (from 0016)
- [ ] **Stopword removal + TF-IDF.** Sharpen signal by removing "I", "my", "will", "to". (from 0016)
- [ ] **Remove personality markers.** "My skeptical nature" appears everywhere in Helen. Strip it. (from 0001/0016)
- [ ] **Different embedding model.** Try bge-small or instruction-tuned models. (from 0008)
- [ ] **Euclidean distance instead of cosine.** Different geometry might reveal structure. (from 0008)
- [ ] **Sentiment-resource features.** Extract (resource, quantity_descriptor) pairs: "zero_bread", "surplus_flour", "low_water". These capture CONTEXT of domain words, not just presence. (from 0022)
- [ ] **Hybrid TF-IDF + embedding.** Concatenate TF-IDF and embedding vectors, then cluster on combined representation. (from 0016)
- [ ] **Agglomerative clustering.** Build a dendrogram — reveals hierarchical structure that flat K-means misses. (from 0014)
- [ ] **PCA on residual vectors.** Combine best embedding techniques — residuals remove shared component, PCA removes noise dims. (from 0013+0015)
- [ ] **Residual + Hebbian.** Co-recall reinforcement on residual vectors might create strong cluster structure. (from 0013+0018)
- [ ] **Residual + K-means.** K-means on residual vectors might partition the spread-out space better than thresholds. (from 0013+0014)

## Rules
- Max 50 experiments. Stop and summarize findings at 50 or when solved.
- Each experiment in its own directory: `experiments/NNNN-description/`
- Each directory contains: `run.py` (script), `output.txt` (full output), `observations.md` (notes)
- Commit after each experiment.
- Use Sonnet subagents for script writing/running to keep costs down.
- Do NOT download or install anything. Use what's already available.
- New ideas get added to the ideas list based on observations, not pre-planned.
- Test data: Helen's 251 entries from `data.pre-abliterated.bak/state.db`
- LLM for labeling: `http://ai-lab.lan:8081/v1` with `/mnt/models/Qwen3.5-27B-GPTQ-Int4`
- Embedding model: `BAAI/bge-large-en-v1.5` via FastEmbedder

## Experiment Log

| # | Name | Concepts | Distinct? | Actionable? | Notes |
|---|------|----------|-----------|-------------|-------|
| baseline | Raw reasoning, bge-large, threshold 0.70 | 1 | N/A | No | Everything collapsed into one mega-blob |
| 0001 | Strip domain vocabulary | 3 (248,2,1) | No | No | Still mega-blob. Vocabulary is not the problem. |
| 0008 | Threshold sweep (0.70-0.95) | N/A | N/A | No | Mean pairwise sim 0.80, unimodal distribution. No sub-structure at any threshold. |
| 0009 | Last sentence only | 206 at 0.70 | Too many | No | Opposite extreme — too fragmented. Conclusions are situation-specific. |
| 0002 | Action-type prefix | 15 at 0.80 | Somewhat | No | Clusters are action-type groupings, not behavioral patterns. |
| 0003 | Two-stage (action→sub-cluster) | ~1 per type | No | No | Within-group sim HIGHER (0.83-0.88). Makes problem worse. |
| 0004 | LLM behavioral abstracts | 15 non-singleton at 0.80 | **YES** | **YES** | **BREAKTHROUGH.** Mean pairwise sim dropped to 0.69. Real behavioral patterns emerge. |
| 0005 | Direct LLM categorization | 10 | **YES** | **YES** | **BEST.** ~10 LLM calls, no embeddings, richest pattern descriptions. |
| 0006 | Two-tier categories | 11 | **YES** | Yes | Clean categories, perfectly stable clustering. But 251 calls for what 0005 does in 10. |
| 0007 | Batch abstracts (10/call) | 13 at 0.75 | **YES** | Yes | Mean sim 0.63 (better than individual). 26 LLM calls. Good middle ground. |
| 0010 | Cross-agent (Jeffery, Adam, Cassandra) | 8-10 each | **YES** | **YES** | Personality-specific patterns emerge. Approach generalizes perfectly. |
| 0011 | Incremental (first half → second half) | 10 | **YES** | **YES** | 90% of second half fits first-half patterns. Distribution shifts show evolution. |
| 0012 | Integration prototype (live pipeline) | 7 | **YES** | **YES** | Full pipeline works: discover, classify, synthesize lessons. Lessons refine over time. |
| 0016 | TF-IDF (no embeddings) | 10 at K=10 | Somewhat | Somewhat | Mean sim 0.19 (4x better than embeddings). Clusters mix action types meaningfully. |
| 0021 | TF-IDF + bigrams | 10 at K=10 | Somewhat | Somewhat | Mean sim 0.09. Even more spread. Similar cluster quality. |
| 0022 | TF-IDF - stopwords | 10 at K=10 | Somewhat | Somewhat | Mean sim 0.12. Domain words dominate — signal is in co-occurrence patterns. |
| 0013 | Residual vectors | 8 at 0.10 | **YES** | **YES** | **BEST EMBEDDING RESULT.** Std 3x better. Genuine behavioral clusters across action types. |
| 0015 | PCA analysis | 10 on 2 PCs | **YES** | Somewhat | Structure IS there in 2-3 PCs. Low-dim signal diluted in 1024D. |
| 0021 | TF-IDF + bigrams | 10 at K=10 | Somewhat | Somewhat | Mean sim 0.086. More spread but similar quality to unigram. |
| 0025 | Sentiment-resource features | 10 at K=10 | **YES** | **YES** | 19 hand-crafted features. Best non-embedding approach. Crisis vs stability clusters. |
| 0014 | K-means (raw + residual) | 8-10 | Somewhat | Somewhat | Residual K=8 best silhouette 0.24. Modest improvement. |
| 0017 | Variance-weighted dims | 10 | Somewhat | No | Top 128 dims: mean sim 0.73. Much weaker than residual approach. |
| 0018 | Hebbian simulation | N/A | No | No | Made dense ball WORSE (mean 0.80→0.85). Needs repulsion mechanism. |
| 0019 | Temporal difference | 10 | No | No | Most balanced sizes but noisy content. "What changed" is too random. |
| 0020 | Sentence decomposition | 15 | **YES** | Somewhat | Sentence-level mean sim 0.60. Clear patterns: "I will decline", "I am critically". |
| 0023 | Personality stripped | 10 | No | No | Barely changes anything (0.797→0.791). Not the cause. |
| 0029 | **Residual + PCA** | 5-10 | **YES** | **YES** | **BEST EMBEDDING.** Silhouette 0.60! 3 PCs on residuals. Multiplicative improvement. |
| 0030 | Residual+PCA cross-agent | 5-8 | **YES** | **YES** | Generalizes: Jeffery 0.44, Adam 0.63, Cassandra 0.54 silhouette. |
| 0031 | Contrastive Hebbian | 8 | **YES** | **YES** | Online reinforcement works: sil 0.52→0.62. Attraction+repulsion on residual+PCA. |
| 0032 | TF-IDF + residual hybrid | 8 | **YES** | Somewhat | Marginal +0.02 improvement. Not worth the complexity. |
| 0033 | Auto K selection | 6 | **YES** | **YES** | Silhouette + Calinski-Harabasz both say K=6 for Helen. |
| 0034 | Tight cliques | 127 | No | No | Overlapping duplicates, word intersection too crude for pattern extraction. |
| 0035 | Structured tuples (regex) | 15 at 3+ | Somewhat | Somewhat | Right concept but regex too brittle — 160 near-duplicate variants. |
| 0036 | Tuple embedding merge | 10 | Somewhat | Somewhat | Two-stage produces better concepts. Regex still weak link. |
| 0037 | Condition+decision split | 10 | **YES** | **YES** | First/last sentence → embed separately → cluster pairs. Genuine IF-THEN rules. |
| 0038 | Behavioral branching | 8×3 | **YES** | **YES** | Same condition → 2-3 different decision patterns. Branch detection works. |
| 0039 | Incremental pipeline | 7 situations | **YES** | **YES** | Online operation: stable from ~100 entries, no batch reprocessing needed. |
| 0040 | Outcome tracking | 6×3 | **YES** | **YES** | Baking resolves crises 3x better than foraging. Empirical outcome data per branch. |
| 0041 | Full pipeline cross-agent | 6×3 per agent | **YES** | **YES** | Personality-specific patterns: Jeffery wastes time messaging, Adam's self-reliance works. |
| 0042 | Action result outcome | 6×3 | **YES** | **YES** | Direct outcome signal: baking 56% positive vs foraging 5% in crisis. |

## Findings Summary (34 experiments)

### Phase 1: The Problem (0001-0009)
Raw bge-large embeddings on diary entries produce a single dense ball (mean pairwise sim 0.80, std 0.075). No amount of vocabulary stripping, threshold tuning, or text preprocessing fixes this. The problem is structural — all entries follow the same reasoning pattern about the same domain.

### Phase 2: LLM Approaches Work But Miss The Point (0004-0012)
LLM categorization (0005) produces rich patterns with ~10 API calls. But this is summarization, not consolidation. The goal is automatic detection via embeddings, not per-batch LLM reasoning. Stanford's generative agents already do this. These experiments are useful as a BENCHMARK for what good output looks like.

### Phase 3: Breaking The Dense Ball (0013-0033)
Three techniques that work:
1. **Residual subtraction** (0013): subtract corpus centroid → std improves 3x
2. **PCA projection** (0015): top 3-5 PCs capture meaningful behavioral axes
3. **Combined residual+PCA** (0029): silhouette 0.60 — multiplicative improvement

Supporting findings:
- TF-IDF (0016): mean sim 0.19, reasonable clusters without any embedding model
- Contrastive Hebbian on residual+PCA (0031): sil 0.52→0.62, works as online algorithm
- Auto K selection (0033): silhouette + Calinski-Harabasz agree on K=6 for Helen
- Variance weighting (0017), personality stripping (0023), temporal diffs (0019): minimal effect
- Naive Hebbian without repulsion (0018): makes the ball WORSE

BUT: broad clusters like "trade evaluation" (76 entries) are categories, not knowledge. Optimizing silhouette scores was a dead end — the goal is actionable knowledge, not clean clusters.

### Phase 4: From Clusters To Knowledge (0034-0042)
The breakthrough: **split each entry into condition (first sentence) and decision (last sentence), embed separately, cluster conditions into situations, sub-cluster decisions into branches.**

This produces:
- **Situation types** (6-8 per agent): recurring conditions the agent faces
- **Behavioral branches** (2-3 per situation): different responses to the same condition
- **Outcome data**: which branch works better (tracked via action results and state changes)

Example consolidated knowledge: "When in crisis with zero bread, baking produces resources 33% of the time vs foraging's 5%. Your default skeptical response (forage) is your least effective crisis strategy."

Validated:
- Cross-agent (0041): personality-specific patterns for Jeffery, Adam, Cassandra
- Incremental (0039): stable online operation from ~100 entries, no batch reprocessing
- Outcome tracking (0040, 0042): empirical effectiveness data per behavioral branch

### Recommended Pipeline For Integration
```
For each agent, maintain:
  - condition_centroid: running mean of all condition embeddings
  - pca_components: top 3-5 PCs of residual condition+decision space
  - situations: list of (centroid, branches, episode_counts)
  - each branch: (centroid, episode_count, outcome_stats)

Every tick (or every N ticks):
  1. New diary entry arrives
  2. Split into condition (first sentence) + decision (last sentence)
  3. Embed both with bge-large
  4. Subtract running centroid (residual)
  5. Project to PCA space
  6. Assign to nearest situation (or create new if below threshold)
  7. Within situation, assign to nearest branch (or create new)
  8. Update outcome stats from action result

Periodically (every 24-72 ticks):
  9. Recompute PCA from accumulated entries
  10. Merge near-duplicate situations/branches
  11. Generate consolidated knowledge summary for prompt injection
```
No per-entry LLM calls. Embedding model already loaded for vector recall.
PCA recomputation is the only batch step (cheap, ~250 entries × 1024 dims).

### What's Left
- [ ] Implement the pipeline in `conwai/cognition/` as a ConsolidationProcess
- [ ] Integrate with existing MemoryCompression or StrategicReview
- [ ] Store situations/branches/outcomes as brain components
- [ ] Test whether injecting consolidated knowledge into prompts changes behavior
- [ ] 18 experiment slots remaining if we need to iterate after integration

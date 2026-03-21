# Consolidation Research

## Current Status: GenAgents-style reflection, FP validated

### Journey

**Phase 1: Embedding experiments (34 experiments)**
Tried to detect episodic→semantic consolidation patterns purely algorithmically via embeddings. Key findings:
- Raw embeddings produce a dense ball (mean pairwise sim 0.80)
- Residual+PCA(3-5) spreads the space (silhouette 0.60)
- Condition+decision split extracts IF-THEN behavioral patterns
- Cross-agent validated, incremental operation works

**Phase 2: Cluster-based integration (abandoned)**
Integrated residual+PCA+k-means into ConsolidationProcess. Added small-model (27B) articulation of cluster patterns. Result: confirmation loop. The system found what agents do repeatedly and told them to keep doing it. A/B test showed consolidation group underperformed control.

**Phase 3: GenAgents-style reflection (current)**
Rewrote ConsolidationProcess to use focal-point questions + retrieval + insight generation, adapted from Park et al. 2023 "Generative Agents." Every 24 ticks:
1. Send last 50 diary entries to 27B: "what are 3 salient questions?"
2. Embed each question, retrieve top-5 relevant diary entries
3. For each question + evidence: "what insight can you infer? One sentence."
4. Store insights as `[Reflection]` diary entries with embeddings
5. MemoryRecall surfaces them with 1.5x similarity boost

### A/B Test Results

**Consolidation vs no consolidation** (backup: `b767da3.data.bak`, 198 ticks, 12 agents)
- Consolidation: +38% bread, +35% trades, net +28 resources
- Control: net -28 resources
- Third-person prompts, observer system prompt

**First person vs third person** (backup: `f467ae7.data.bak`, 400 ticks, 20 agents)

Both groups had same observer system prompt, only differed in output person.

| Metric | First Person | Third Person |
|--------|-------------|-------------|
| Alive | 10/10 | 9/10 (Adam dead) |
| Avg hunger | 79.9 ± 1.6 | 71.3 ± 23.8 |
| Avg bread (end) | 26.6 | 14.4 |
| Zero bread agents | 0/10 | 5/10 |
| Avg coins | 101 | 181 |
| Bread Q1→Q4 | 424→848 (improving) | 648→496 (collapsing) |

Key findings:
- FP started weaker but improved over time. TP started stronger but collapsed.
- TP agents hoarded coins while starving (Helen: 345 coins, 0 bread; Adam died with 215 coins)
- FP reflections are self-critical ("I failed because...") → drive course correction
- TP reflections are analytical ("the agent employs...") → narration loops, agents describe strategy while dying
- FP agents inspect cross-group more (68% vs 41%) — more outward-looking
- FP agents formed emergent partnerships (Danielle+Jill announced a trade alliance on the board)
- FP agents have higher offer conversion (168 offers → 158 trades) vs TP (108 offers → 160 trades)

**Confound note:** An earlier FP vs TP test (different system prompts per group) showed FP losing badly. The system prompt identity ("you observe an agent" vs "write in first person") was the confound, not the person. Once both groups got the same observer system prompt, FP won clearly.

### Known Issues
- 1.5x reflection boost too aggressive — crowds out real diary memories (5/5 recalled as reflections at 159 candidates)
- No semantic dedup — near-duplicate reflections accumulate each cycle
- Reflections stored in same diary list as regular entries — should be separate for cleaner dedup and controlled recall ratio
- All insights generated even if semantically identical to existing ones (exact-match dedup only)

### Backup Index

Pre-squash commit hashes (originals no longer in git history):
- `0001-0006.data.bak` — cluster-based consolidation runs (pre-reflection rewrite)
- `b767da3.data.bak` — consolidation vs control, third-person, 198 ticks, 12 agents
- `f467ae7.data.bak` — FP vs TP, 400 ticks, 20 agents

Post-squash, all consolidation code lives in main commit `1a0fdb6`.

### Next Steps
- [ ] Separate reflection storage from diary for semantic dedup and controlled recall ratio
- [ ] Reduce 1.5x boost or cap reflections per recall (e.g. max 2 of 5)
- [ ] 3-way A/B: FP consolidation vs TP consolidation vs no consolidation
- [ ] Importance-based reflection trigger (instead of fixed 24-tick interval)
- [ ] Retrieval scoring: add recency + importance alongside similarity

### Research References
- Park et al. "Generative Agents" (2023, arxiv 2304.03442) — reflection mechanism, memory stream
- Pink et al. "Episodic Memory" (2025, arxiv 2502.06975) — 5 properties, consolidation framing
- SimpleMem (2026, arxiv 2601.02553) — hybrid retrieval, admission gating
- MemGPT/Letta (2023, arxiv 2310.08560) — sleep-time compute, self-editing memory
- A-MEM (2025, arxiv 2502.12110) — Zettelkasten, memory evolution
- Nemori (2025, arxiv 2508.03341) — predict-calibrate, event segmentation
- CLIN (2023, arxiv 2310.10134) — causal abstractions
- Howard & Kahana "Temporal Context Model" (2002) — context drift, semantic emergence

## Embedding Experiment Log (Phase 1)

| # | Name | Concepts | Distinct? | Actionable? | Notes |
|---|------|----------|-----------|-------------|-------|
| baseline | Raw reasoning, bge-large, threshold 0.70 | 1 | N/A | No | Everything collapsed into one mega-blob |
| 0001 | Strip domain vocabulary | 3 (248,2,1) | No | No | Still mega-blob |
| 0008 | Threshold sweep (0.70-0.95) | N/A | N/A | No | Mean pairwise sim 0.80, unimodal |
| 0009 | Last sentence only | 206 at 0.70 | Too many | No | Too fragmented |
| 0002 | Action-type prefix | 15 at 0.80 | Somewhat | No | Categories not patterns |
| 0003 | Two-stage (action→sub-cluster) | ~1 per type | No | No | Within-group sim HIGHER |
| 0004 | LLM behavioral abstracts | 15 at 0.80 | **YES** | **YES** | BREAKTHROUGH |
| 0005 | Direct LLM categorization | 10 | **YES** | **YES** | BEST but it's summarization |
| 0006 | Two-tier categories | 11 | **YES** | Yes | 251 calls |
| 0007 | Batch abstracts (10/call) | 13 at 0.75 | **YES** | Yes | Good middle ground |
| 0010 | Cross-agent | 8-10 each | **YES** | **YES** | Personality-specific |
| 0011 | Incremental | 10 | **YES** | **YES** | 90% second half fits first-half patterns |
| 0012 | Integration prototype | 7 | **YES** | **YES** | Full pipeline works |
| 0013 | Residual vectors | 8 at 0.10 | **YES** | **YES** | BEST EMBEDDING RESULT |
| 0014 | K-means | 8-10 | Somewhat | Somewhat | Modest improvement |
| 0015 | PCA analysis | 10 on 2 PCs | **YES** | Somewhat | Structure in 2-3 PCs |
| 0016 | TF-IDF | 10 at K=10 | Somewhat | Somewhat | No embeddings needed |
| 0017 | Variance-weighted | 10 | Somewhat | No | Weaker than residual |
| 0018 | Hebbian simulation | N/A | No | No | Made dense ball WORSE |
| 0019 | Temporal difference | 10 | No | No | Too random |
| 0020 | Sentence decomposition | 15 | **YES** | Somewhat | Clear patterns |
| 0021 | TF-IDF + bigrams | 10 | Somewhat | Somewhat | More spread, similar quality |
| 0022 | TF-IDF - stopwords | 10 | Somewhat | Somewhat | Domain words dominate |
| 0023 | Personality stripped | 10 | No | No | Barely changes anything |
| 0025 | Sentiment-resource features | 10 | **YES** | **YES** | Best non-embedding |
| 0029 | **Residual + PCA** | 5-10 | **YES** | **YES** | **BEST: silhouette 0.60** |
| 0030 | Residual+PCA cross-agent | 5-8 | **YES** | **YES** | Generalizes |
| 0031 | Contrastive Hebbian | 8 | **YES** | **YES** | Online: sil 0.52→0.62 |
| 0032 | TF-IDF + residual hybrid | 8 | **YES** | Somewhat | Marginal improvement |
| 0033 | Auto K selection | 6 | **YES** | **YES** | K=6 optimal for Helen |
| 0034 | Tight cliques | 127 | No | No | Overlapping duplicates |
| 0035 | Structured tuples | 15 | Somewhat | Somewhat | Regex too brittle |
| 0036 | Tuple embedding merge | 10 | Somewhat | Somewhat | Regex still weak |
| 0037 | Condition+decision split | 10 | **YES** | **YES** | IF-THEN rules |
| 0038 | Behavioral branching | 8×3 | **YES** | **YES** | Branch detection works |
| 0039 | Incremental pipeline | 7 | **YES** | **YES** | Online from ~100 entries |
| 0040 | Outcome tracking | 6×3 | **YES** | **YES** | Baking 3x better in crisis |
| 0041 | Full pipeline cross-agent | 6×3 | **YES** | **YES** | Personality-specific |
| 0042 | Action result outcome | 6×3 | **YES** | **YES** | Baking 56% vs foraging 5% |

# Experiment 0001: Strip Domain Vocabulary

## Hypothesis
Removing resource-specific words (flour, water, bread, etc.) would force the embedding model to cluster on intent/action patterns rather than shared topic vocabulary.

## Results
| Clusters | Sizes |
|----------|-------|
| 3        | 248, 2, 1 |

Still a mega-blob. 248 of 251 entries in one cluster. The 2 outliers were voting-related entries.

## Analysis
**Stripping vocabulary does not help.** The entries are semantically similar at a level beyond word overlap. The embedding model captures:
- Similar reasoning STRUCTURE (assess situation → decide action → justify)
- Similar INTENT (resource management decisions)
- Similar TONE (skeptical, deliberate — Helen's personality)

Even with domain words removed, the stripped text still reads like "I need to... so I will... because my [personality trait] demands..." — same structure every time.

## Key Insight
The mega-blob is NOT a vocabulary problem. It's a structural/intent similarity problem. The entries genuinely ARE similar from the embedding model's perspective — they're all "agent reasoning about what to do next in a resource game."

## Implications
- Simple text preprocessing (word removal, stemming) won't fix this
- Need to change WHAT we embed, not just clean up the text
- Need to represent entries at a different level of abstraction

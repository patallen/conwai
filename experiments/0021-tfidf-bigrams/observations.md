# Experiment 0021: TF-IDF with Bigrams

## Results
- unigram+bigram shape: (251, 4284), mean sim: 0.086 (vs 0.186 unigram-only)
- Even more spread out with bigrams — good
- K=10 clusters similar quality to unigram TF-IDF

## Interesting bigrams (5-50 doc frequency)
"to_secure"(48), "will_forage"(45), "skeptical_of"(45), "critically_starving"(44), "strategy_prioritizes"(45)

## Analysis
Bigrams spread the space further (mean 0.086) but the clusters are qualitatively similar to unigram. The top bigrams are still domain-universal ("i_will", "i_am", "bread_and"). Need to combine with stopword removal for bigrams to add real value.

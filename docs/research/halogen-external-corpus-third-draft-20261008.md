# External-corpus third-draft CPU screen

One fixed external-corpus policy produced **2 candidates in 15 rounds, with 0 useful third-token matches**. In the 10 rounds whose first two native MTP suggestions were correct and whose third target label was available, both available candidates were wrong. This corpus/policy supplies no evidence supporting a serving candidate. It remains disabled.

The independently frozen War and Peace prefix contains **259,938 raw token IDs**. It comes from the prior 260,000-token served-input preparation; the raw corpus excludes that request's chat frame and task. The query uses the last committed ID followed by the two actual native pending IDs. The exact trigram chooses the most frequent following corpus ID, breaking ties by lowest ID, with minimum frequency 1 and no backoff. Policy/corpus selection preceded scoring; future completion labels were never indexed. A third match after an incorrect pending pair cannot increase accepted tokens.

The observed fixture is one **Halogen 0.16.2** request family, with 14 complete third labels and one incomplete final round. Exact tokenizer pins also match 0.17.2, and all 8,191 comparable native prompt IDs match the actual retained request render. This establishes token identity; it does not establish current 0.17.2 acceptance or throughput.

At base 8199, the corpus supplies 4776 instead of authoritative 2018; at base 8215, it supplies 13240 instead of 12515. Each trigram occurs once. Neither frequency rules nor corpus selection changed after these outcomes. The joint useful extension count is 0/10 eligible rounds and 0/2 candidates. These fixture counts are not population estimates.

The initial preprocessing attempt failed under an unnecessarily tight baseline-plus-128-MiB cap. Its artifacts remain intact. One corrected attempt with **512 MiB total process and job caps** succeeded using the same corpus, mapping and policy. Final peaks were 240,238,592 B private memory and 246,673,408 B working set. No unchanged screen was repeated.

No engine, GPU, NPU, WSL or API request ran for this screen. Offline preprocessing time is not serving lookup latency or tok/s. There are no current 0.17.2 Prefill, Decode or acceptance measurements from this candidate. An independent causal review and all per-case outcomes are pinned in the companion JSON.

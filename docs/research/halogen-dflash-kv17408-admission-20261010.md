# Halogen 0.17.3: KV17408 diagnostic admission

Tool session 6846 ended with exit 1. The smaller diagnostic context/KV pool
started successfully, but the frozen natural 16,384-input / 128-output request
was not submitted because request-entry reserve failed. Candidate-ready showed
21.978210 GiB physical and 113.107372 GiB commit headroom; the exact later
rejecting frame was not retained. The ready snapshot is not that rejecting frame.

Only context/KV capacity changed from 32,768 to 17,408; chunk/arena 8,192,
native diagnostic image, assets, runtime, driver, workload and admission floors
remained fixed. The expected 453,120,000-byte KV reduction is a source estimate,
not a measured reclaim amount or speed improvement.

Retained native runtime confirms zero Request births and zero feature exports.
There is no birth-predicate finding and no new prefill, decode, acceptance or NPU
tok/s measurement. The trial is terminal and must not be repeated unchanged.

Normal context 262,144 serving was restored and verified ready/open. The trial
contains 17 retained runtime files, terminal-checkpoint.json and the stable
normal-preserved-after-terminal.json verification. Own coordinator handles closed.

Next concrete candidate: scoped advice for the already copied drafter/full-head
CPU maps only, after synchronized GPU copies and final source identity checks.
Embedding storage and all GPU tensors remain. No reclamation or admission gain
is established until that distinct candidate is measured.

# Direct SSD lookup placement preparation — 4 October 2026

The complete lookup table is now extracted to E: with a canonical receipt.
It has not yet passed independent full readback or the ordinary lookup-source
qualifier. No SSD placement throughput or acceptance result is claimed.

The root-owned process-observer diagnostic completed in 758.64 guest seconds.
It copied 51,200,245,764 payload bytes from the existing pinned w4b checkpoint
into a standalone 51,200,246,144-byte HGN v2 file. Payload XOR32 was verified;
payload and whole-output SHA-256 were computed during the bounded copy.
Source native identity was identical before and after extraction.

The output is
`/mnt/e/AI/halogen-experiments/lookup-direct-20261004/263bf3b410474d07bfc03b59945bfada/ngram.hgn`.
The payload SHA-256 is
`c42900db1bef0d9a688241031f614e179752b0463f822dc07a197b1a42493d8c`;
whole-output SHA-256 is
`3343a193cb2e1fe68fac83a42b49176621174abb1cc57ba67e2ab149ead80575`.

The new coordinator preserves the earlier failed threaded diagnostic. It uses
an owned observer process created before NumPy import and a nonblocking
anonymous pipe containing advancing host sequences. It retains the same
two-second observation lease and 18-GiB physical/commit floor. Source clean
ranges are reclaimed after each 8-MiB read; owned output clean ranges are
reclaimed after each 64-MiB fsync. No model or inference engine executes.

The success tests a process-observer variant. It does not establish that GIL
contention or heartbeat-file transport caused the earlier thread refusal.

The retained WSL child exited 0. Guest observer exit/wait status is 0; guest
and host observers and the owned child are terminal, with no guard errors.
Minimum physical/commit headroom was 44.05813 / 198.34660 GiB. Partial artifacts
from older runs remain preserved and unqualified.

Artifacts are under
`server/.local/optimization9h-20261004/lookup-direct-process-diagnostic-263bf3b410474d07bfc03b59945bfada`.

| Artifact | SHA-256 |
| --- | --- |
| New ignored coordinator | `599cc37c6da99683ec6ab3c87325fa71e00b41984c23d1a19a2d5de270235261` |
| Unchanged tracked extractor | `ee50352404a1de5f7b8fe6dae356cd5a4abbbcfb89e39cbf033b3893fd47811a` |
| Root-generated guest worker | `7431265622b4d2abf87dcefbfbc73b79931ce5b9719592fa5a11eedef9073a8e` |
| Canonical extraction receipt | `067f2f7c847ca9b358767bd8699176c1d94994f21335618abc7f9bf4bea78e4a` |
| Terminal result | `60a2525dadce5d03a63fe1373a1d440eb4d8f23d0ec112db05760a3818f10d7a` |

Next is a bounded full readback bound to the successful receipt and exact file
identity, followed by ordinary qualification. Only then may a matched stock /
SSD / stock engine comparison use this file.

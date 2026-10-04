# Direct SSD lookup placement preparation — 4 October 2026

The complete lookup table is extracted to E: with a canonical receipt and has
passed independent full readback and ordinary lookup-source qualification.
No SSD placement throughput or acceptance result is claimed yet.

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

## Completed independent readback and qualification

The separate owned supervisor consumed all 51,200,246,144 bytes in a bounded
355.72-second guest readback. The complete hash matches extraction; source and
output metadata match before and after. Reader, observer, host monitor and
retained WSL process are terminal with zero exit codes and no guard errors.
Minimum physical/commit headroom was 44.20246 / 198.04909 GiB.

The original readback coordinator refused before a WSL launch because Windows
Path.stat and fstat report different ctime fields. A new preserved-source
variant compares explicit Windows birthtime across handle/path APIs, retaining
fd ctime stability before/after, size/inode/mtime, no-links and bounded hash
checks. The original frozen sources remain unchanged.

A separate owned qualification process replaced only the in-memory
`lookup_source.guarded_hash` callback with the reviewed receipt-bound readback
result. It called the ordinary `lookup_source.qualify`, which rechecked current
metadata and wrote its normal immutable identity seal. The callback was restored,
the owned job closed with exit 0, and no model or NPU executed. The 18-GiB floor
held (minima 44.70123 / 198.94180 GiB).

| Artifact | SHA-256 |
| --- | --- |
| New readback coordinator | `6315e08afd264154a3a57cabcd6a6770add01cdb3a6bddd7a6ba2280c581921e` |
| Readback root result | `a06b9bbf55935e20537a3791b6783ae92096bff35a3d35c2437eb3f3e211e2d4` |
| Readback guest receipt | `f9dd15fcc02b552f8aa9af25eedd70db17bfbb8dc704ba60540667b5655fc854` |
| Isolated qualifier source | `a755d92c16e3cbfeb6b029005aaf85921e712fb5aa14e4a2d99f8936216ddc67` |
| Ordinary qualification result | `4061c198df13750f95389e7071c6d31f3774f84891d2e072ca65c803eeb60da5` |

Readback artifacts are under
`server/.local/optimization9h-20261004/lookup-direct-readback-cf523e689d7a4f918d83a10b23b022b5`;
qualification artifacts are under
`server/.local/optimization9h-20261004/lookup-direct-qualification-fc2735ea5a5d4cc1bdef619981f1004a`.

A new prepared placement coordinator preserves the older ext4-labelled source
and corrects its descriptive label to direct E: NTFS through 9p. Compute/cache
settings are unchanged: capacity 65536, input 32768, Exact cache, MTP depth 2,
two three-turn repetitions, stock A / candidate / stock B. Prepared state
SHA-256 is `f573a5ef8215f100352aaedc32391408bdcb4affcda08a9231ac2fbd9d9645cb`;
coordinator SHA-256 is
`086d6bd3800eb4a9ff4b838a510cb0410c8ee19198aceef4a4211d700101658a`.
The new matrix state has its own name. Root started it at 03:57 UTC; at 04:03
UTC the first stock cell was serving its second repetition, with three of six
request samples retained. The full stock A / candidate / stock B comparison is
still running and has no qualified placement result yet.

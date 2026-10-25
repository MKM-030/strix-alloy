# Halogen 0.18.15: explicit native lookup placement

The adapter can select one previously verified n-gram table wrapper on native
WSL storage. This changes the table's filesystem placement. It does not change
weights, arithmetic, draft policy, GPU kernels or the table payload. The feature
is off unless an explicit canonical lookup receipt is selected. This note
documents qualification and ownership; it claims no new token-rate gain.

The ordinary configuration keeps using the installed complete w4b file as its
lookup source. A selected candidate retains that stock source's mount and full
integrity verification, then adds the canonical wrapper as a read-only bind at
`/candidate/ngram.hgn`. `HALOGEN_NGRAM_TABLE` selects that extra bind. Omitting
the lookup receipt retains the ordinary configuration; an invalid explicit
receipt fails rather than silently falling back.

## Canonical content and retained readback

Only the following extraction receipt and exact SHA-256 are admitted:

`server/.local/optimization9h-20261004/lookup-native-copy-9447b9641f964497980fcb281b18a5c3/extraction.receipt.json`

`df0dc1e5d2de921b58c4f18f988624687191ec6f80e2336c90c7de454144c7fb`

The native table file is
`/home/revn/halogen-experiments/lookup-native-20261004/9447b9641f964497980fcb281b18a5c3/ngram.hgn`.
Its complete-file size is **51,200,246,144 bytes**, with SHA-256
`3343a193cb2e1fe68fac83a42b49176621174abb1cc57ba67e2ab149ead80575`.
The table payload is the unchanged
`layers.1.ple.ngram_embedding.weight`, storage 10, dimensions
`[128, 2500012, 160]`, variant 0 and 51,200,245,764 bytes. Payload SHA-256 is
`c42900db1bef0d9a688241031f614e179752b0463f822dc07a197b1a42493d8c`.

The port reuses the completed payload readback seal retained under
`backends/halogen-wsl2-0.16.2/.local/lookup-qualifications/`:

| Binding | Exact value |
| --- | --- |
| Cache key / filename stem | `cad72bf989a3e695a74c64e83b5974ebd81dd9ee69483601a57243d67de3b9be` |
| Small seal file SHA-256 | `f9f4c87a4e01eca7861221f19ccf7c3da87a7b45f602be29d4d0aa5d832d4d3d` |
| Complete original w4b source bytes | `124068083904` |
| Original source SHA-256 | `9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6` |

That old small seal remains a required dependency. Its exact bytes and canonical
cache key must match. The current source and wrapper must still match all five
retained file identity fields: size, device, inode, modification nanoseconds and
change nanoseconds. Bounded metadata also validates canonical source/wrapper
headers and tensor entries. Missing or changed content does not trigger a new
50-GB readback, replacement seal, download or cache write.

## Fresh engine binding

The schema-2 qualification seal binds the exact 0.18.15 image and ELF:

- Image: `ghcr.io/peonist-ai/halogen-flash-server@sha256:cde6ae91ab3497a470c848fd5c509b0f4af659a1dea7e74b8789df82cde0510e`
- ELF SHA-256: `ce1c375eb2d92a4c7b2b0e1d969acd865bb72bb248c52498eedb170cbaea8a89`
- HGN loader function `[0x1e9f1a0, 0x1e9fc68)` SHA-256:
  `1c24f6ab85a7036a4a09cfd2ba711ffc9a02787c2bfdbdc8646f1a248be5c871`

Fresh finite inspection establishes the current loader's 104-byte `HGN1`
header, accepted versions 1/2, exact declared file extent, 160-byte entry stride
and entry offset/extent bounds. It maps the entry storage, dimension count,
dimensions, byte extent, checksum and variant into the runtime descriptor. The
explicit `HALOGEN_NGRAM_TABLE` success path invokes this constructor. This
function does not independently assert every canonical dimension value; the
pinned receipt and bounded metadata bind those values. Static loader binding
does not establish live inference correctness or speed.

The fresh qualification fields are:

| Field | Purpose |
| --- | --- |
| `schema` | `2`, the current engine-bound seal format |
| `configuration` | Exact canonical receipt path and SHA-256 |
| `source`, `tensor`, `output` | Retained content and file-identity bindings |
| `read_mode` | `trusted-canonical-cache` |
| `reserve_gib` | `18`; no reserve relaxation |
| `engine_binding` | Exact version, immutable image, ELF and current HGN-loader hash |
| `payload_qualification` | Exact retained small readback seal key and SHA-256 |
| `mount_binding` | Native destination/source and `readonly: true`, plus retained stock destination/source |

Qualification checks fresh metadata before lifecycle setup. Metadata is checked
again after memory admission before container creation and immediately before
model startup. Normal checkpoint verification still checks the complete v2
checkpoint and the complete original w4b lookup source.

## Runtime ownership and memory

The manifest contains the complete qualification seal. The normal command emits
`readonly` for every bind mount. Running-container ownership validation compares
the actual bind source, destination and type, requires Docker `RW` to be false,
and checks the actual environment against the admitted manifest. A manifest's
`readonly: true` field alone is only a plan, not evidence about a live container.
The bind-source, seal and environment checks remain part of the bounded asynchronous
ownership inspection; no additional WSL metadata task is added to every poll.

No additional pinned table or GPU allocation is introduced. The approximately
47.68-GiB table is demand-paged from a different filesystem. Existing page-cache
residency and file-cache history can vary and must be considered in comparisons.
The **18-GiB physical and commit reserve remains continuous**, the **22-GiB request
entry reserve remains**, and startup admission, cgroup limit, guard cadence and
lease duration are unchanged. The port also leaves prefill limits, MTP, PLD,
prefetch and private HSA/matmul policies unchanged.

The focused CPU tests cover retained-cache reuse, fresh identity failure,
stock-source preservation, unchanged service settings, explicit table selection,
read-only command construction and rejection of actual writable or changed
runtime bindings. Their metadata boundary is mocked; they make no WSL, device,
engine or model/table readback requests. A runtime comparison must separately
verify outputs, actual token counts, Prefill, Decode, acceptance and request time.

## Measured control / canonical / control bookend

The 25 October 2026 experiment used Halogen 0.18.15, the unchanged v2 checkpoint,
32K context/pool, one slot, 8K chunk/arena, adaptive MTP and prefetch off, with
Vision On and Thinking Off. Each arm excluded one warmup and measured three
requests per case. PP1 was a separate serial 8192-input/1-output case; the other
two cases generated 128 tokens with MTP. Canonical selection changed only lookup
placement. The frozen requests, all generated output strings and combined and
head/lookup/grammar draft counts matched across all three arms.

| Case | Control A HTTP mean (s) | Canonical B HTTP mean (s) | Restored control A′ HTTP mean (s) | A′ drift from A |
| --- | ---: | ---: | ---: | ---: |
| 8K MTP128 | 9.479524 | 9.331017 | 9.773013 | +3.10% |
| 16K MTP128 | 17.007012 | 16.508018 | 18.588014 | +9.30% |
| 8K serial PP1 | 6.721719 | 6.862613 | 7.692902 | +14.45% |

HTTP measurements use independent Windows QueryPerformanceCounter intervals.
The restored control drift, sequential arm order and file-cache history prevent
a clean placement-effect estimate. The ordinary lookup configuration remains
selected; the canonical option is not promoted to the default.

The six measured control requests per case, pooled across A and A′, give:

| Case | Native processed-prefill (tokens/s) | Native decode (tokens/s) | HTTP mean (s) | Accepted / drafted |
| --- | ---: | ---: | ---: | ---: |
| 8K MTP128 | 1189.59 | 47.56 | 9.626268 | 420 / 636 (66.04%) |
| 16K MTP128 | 1133.20 | 39.66 | 17.797513 | 354 / 672 (52.68%) |
| 8K serial PP1 | 1141.38 | N/A | 7.207311 | N/A (0 / 0) |

Native phase clocks are observations, not independently clock-qualified rates.
Pooling here means total phase tokens divided by total phase time; HTTP means
use all six complete-request samples. This aggregation describes the measured
control history and does not remove its drift. Every sample and the original
three-arm comparisons are retained under
`server/.local/halogen-update-20261025/primary01815/optimization-next/measurements/`
in `lookup-aba-bookend-analysis.json` and `lookup-control-pooled-six.json`.

The final interleaved serial/MTP 60-request suite on the restored control passed
accounting, output identity and complete-request QPC checks. The native MTP
arithmetic mean was 50.13 tokens/s (pooled: 48.78). Complete-request QPC output
rates were 28.29 tokens/s for serial and 48.62 for MTP. Serial processed all 867
input tokens; the following MTP requests reused all 867 from cache. The observed
1.719-times whole-request speed ratio therefore does not isolate an MTP-only
effect. Combined acceptance was 4830/6804 (70.99%). The full results and scope
limitations are in [the comparison report](../benchmarks/halogen01815-comparison-20261025.md).
Thinking Off follows the published performance row; the upstream `low`-effort
command alone does not establish that condition. The published 65.88 tokens/s
result on a different platform/configuration is not locally confirmed.

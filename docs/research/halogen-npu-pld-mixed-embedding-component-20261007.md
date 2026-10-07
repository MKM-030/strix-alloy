# Native PLD batch versus prepared prefix and correction component — 7 October 2026

The finite [component source](../../scripts/benchmarks/halogen0162_pld_mixed_embedding_replay.c)
compares original GPU embedding batches for k2/k3/k4 with original GPU prepared
prefix rows and one native correction row. Both paths execute the original
full-k seed. Root compiled the sealed source successfully with `-O2 -Wall
-Wextra -Werror`; the retained compile receipt explicitly records
`hardware_executed=false`. Root subsequently completed one finite GPU run:
120/120 recorded exact-parity pairs passed and all24saved output hashes and
12stock/mixed output pairs were independently rechecked offline. The
[result and budget decision](halogen-npu-pld-mixed-embedding-result-20261007.md)
retire this candidate for the current effort: mean branch savings are only
0.2–17.6µs across six cases, with order/outlier sensitivity.
This component establishes no NPU, live table, full-head, acceptance or decode
speed qualification.

The [offline row planner](halogen-npu-pld-mixed-embedding-plan-20261007.md)
remains default-off. This component supplies the missing finite original
M2/M3/M4 versus assembled M1-prefix/M1-tail oracle. It does not install that
planner or change the engine's host dispatcher.

## Sealed source and compiler evidence

| Artifact | SHA256 |
|---|---|
| `halogen0162_pld_mixed_embedding_replay.c` | `a1c45e8c2594886b9f0e9dfe5fe7acfe3cf3f43e87c3b3e804123f212d6f1aee` |
| Unchanged included `halogen0162_fc_replay.c` | `8535dbe608b49f8bbad8a962359de59e78df1bd0b9cae922045277b6a1d77826` |
| Root-compiled binary | `85d806d41f1366d6f20f0bac199c2a3d9814e4cb686f2b86d9261d484c8ee8e3` |
| [Pinned image wrapper](../../scripts/benchmarks/halogen0162_pld_mixed_embedding_image_wrapper.py) | `8eeccd646e784bb0ead438eea2c3064b3090502eecff7b2599ed2dd785351953` |

The compile work directory is
`server/.local/optimization9h-20261004/owned-compile-b020a132759d4376997ebfb0548a0dd9`.
Its `result.json` records both owned commands returning zero, closed owned
jobs, both source pins, `passed=true` and no hardware execution.
`command-1.stdout` retains the binary digest at
`/home/revn/halogen-re/pld-mixed-embedding-c63387a12c634fe9ad00b63878d1708a`.
The compile plan SHA256 is
`d0542450a0dd1ee2788d7b9b03a2a24dc39d4543fb716f9c441bfc7b9e6c7401`.

The compile definition binds the mixed source digest. The compile envelope
also binds the unchanged included FC source. The renamed FC entry is never
called; the mixed component reuses its bounded immutable-file and HIP scaffold.
Frozen v1/v2/v3 handoff sources remain unchanged.

## Fixed rows and original kernels

The harness uploads a private two-row raw BF16 table containing the retained A
and B fixture inputs. IDs0/1 are **synthetic indices into this private table**;
they are not native vocabulary IDs and do not prove live table/token lineage.
The gamma and original Q8 matrices have independent frozen pins. Hidden inputs
are the retained original-native normalized A/B rows.

Setup uses the original gather and RMS to normalize both raw rows, verifies
their frozen normalization hashes, then uses original M1 embedding projection
and original M4 hidden projection to build resident A/B atlases. Each case
uses original gather to assemble its prepared prefix slab and common hidden
batch before timing. No prepared prefix is supplied by an NPU in this test.

| Case | Ordered fixture rows | Prepared prefix | Native correction |
|---|---|---|---|
| A-k2 | A,B | A | B |
| B-k2 | B,A | B | A |
| A-k3 | A,B,A | A,B | A |
| B-k3 | B,A,B | B,A | B |
| A-k4 | A,B,A,B | A,B,A | B |
| B-k4 | B,A,B,A | B,A,B | A |

The stock embedding branch is full-k raw gather, in-place RMS and the original
Mk embedding FC symbol. The mixed branch is grid1 gather from ID offset
`4*(k-1)`, in-place RMS at raw input offset `5120*(k-1)`, and original M1 FC
into the correction slot of the private slab. Each then executes the original
seed with full count k, its E pointer and the same prepared native hidden
batch. E stride is5120bytes; each hidden/seed row is20480bytes.

The loaded original HSACO provides gather, RMS, M1/M2/M3/M4 and seed. Every
launch uses block256/default stream; FC uses grid160. The engine's host
dispatcher is not executed. The original engine and embedded HSACO are
independently hashed and compared byte-for-byte at the frozen engine offset.
The harness requires exactly one gfx1151 device with wave32, and rejects
`HALOGEN_LQ8_WAVE` unless unset or exactly`1`.

## Finite timing and arithmetic contract

Each of six cases has four warmup and sixteen measured stock/mixed pairs:
120pairs total, of which96pairs contribute to measured means. Execution order
alternates between stock-first and mixed-first. Three reusable events delimit
start, embedding end and full-seed end for each path. The report retains each
pair's B(k), T(1), seed, total and host enqueue/wait intervals, plus per-case
mean B−T and total stock−mixed delta.

Initialization, prefix/hidden assembly, copies, poison, readbacks, output
validation, report writing and cleanup are excluded from GPU event intervals.
No concurrent producer, NPU, transport, readiness lookup or live validation
cost is measured. In a live implementation the ready-round budget would be
`B(k)-T(1)-C-J`, where C is added validation/seed rewrite and J is concurrent
preparation/transport contention. This experiment measures only the isolated
GPU component budget; a positive result alone cannot establish decode gain.

Before every pair, the stock E and both seed outputs are poisoned. Only the
mixed slab's correction slot is poisoned; its prepared prefix remains intact.
After both event waits, untimed readbacks require byte-exact full E parity,
byte-exact full-k seed parity, every E row matching its frozen original M1
output, finite filled outputs and repeat-stable seed bytes. There is no
tolerance, fitting or alternate arithmetic reference. A tiny/nonpositive
component delta offers no supported live optimization budget.

Expected successful receipt counters are:

| Counter | Expected |
|---|---:|
| Completed pairs / exact parity pairs | 120 / 120 |
| Original launches | 978:18 setup +960 timed |
| Copies | 972:12 initial/setup +960 poison/readback |
| Setup synchronizations | 8 |
| Device allocations / frees | 17 / 17 |
| Module loads / unloads | 1 / 1 |
| Event creates / destroys | 3 / 3 |
| Event records / elapsed calls | 720 / 720 |
| Event waits | 240 |
| Cleanup device drain | 1 |
| Binary outputs | 24 |

Each case writes stock/mixed embedding and seed files, such as
`A-k2-stock-embedding.u16`. The exclusive output report is `mixed-replay.json`,
schema `halogen0162.pld-mixed-embedding-component.v1`. Cleanup drains queued
work, destroys events, frees every allocation, unloads the module and closes
files/library before rechecking all immutable input identities and hashes.
The owned receipt records every expected counter above and120/120exact
parity. The separate result report distinguishes those intermediate device
checks from the independently rehashed24saved final files.

## Root-owned pinned image command

The wrapper reuses six helper implementations from the frozen RMS wrapper
unchanged: SHA validation, requirements, file identity, bounded no-follow file
binding, installed-HIP selection and exclusive JSON persistence. It pins its
own independently supplied source SHA, both C sources, the compiled binary,
original engine/codeobject, original bridge, installed HIP, both fixture
manifests and seven input files. It records `runtime.json` before `exec` and
uses no provider acquisition or retry. Its guard flag acknowledges the root's
outer process/container/deadline/reserve guard; it performs no host-server
observation itself.

Mount these locations read-only:

- `/candidate`: wrapper, `replay`, `flash_serve`, `engine-gfx1151.hsaco`,
  `halogen0162_pld_mixed_embedding_replay.c`, `halogen0162_fc_replay.c`.
- `/fc-fixtures`: retained
  `fc-fixtures-f47a1312c34f47b6a23188247f46741b` directory.
- `/rms-fixtures`: retained
  `embedding-rms-fixtures-78c49b8e265c4de9adb9c0cf3cc8254e` directory.

Use a fresh writable `/result`. The C harness creates `/result/native`
exclusively; the outer controller must not precreate that child directory.
Only root invokes this command after its lifecycle checks:

```text
python /candidate/halogen0162_pld_mixed_embedding_image_wrapper.py
  --source-sha256 8eeccd646e784bb0ead438eea2c3064b3090502eecff7b2599ed2dd785351953
  --outer-exclusive-gpu-guard
```

The C interface is exactly nineteen arguments after executable, argc20:

```text
ENGINE HSACO HIP_LIBRARY HIP_SHA
E_WEIGHT E_SHA H_WEIGHT H_SHA
A_RAW A_RAW_SHA B_RAW B_RAW_SHA GAMMA GAMMA_SHA
A_H_NORM A_H_SHA B_H_NORM B_H_SHA NEW_OUTPUT_DIRECTORY
```

The installed regular HIP library is selected inside
`/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib` and must hash to
`6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5`.
The bridge `/usr/lib/librocdxg.so` must hash to
`0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6`.
Exact native argv, actual library path, input identities and hashes are
retained in the wrapper record.

The FC fixture manifest SHA is
`ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11`;
the RMS manifest SHA is
`cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246`.
The wrapper's command order selects raw A/B embeddings from the RMS mount,
raw gamma from that mount, and Q8 weights plus hidden normalized rows from
the FC mount. The seven direct input pins are also enforced by the C harness.

## Offline verification status

Four focused Windows standard-library tests cover the exact nineteen-argument
order, all seven frozen fixture bindings, rejection of normalized/escaped
embedding paths, and rejection of changed gamma/hidden hashes. The initial
missing-wrapper run failed all four assertions; the implementation passed all
four, exit0. A Windows AST comparison verified the six reused helpers match
the frozen RMS wrapper exactly. Neither check invokes the wrapper run path,
executes a native binary, enters WSL, acquires a provider or uses a device.
Native compilation is proved by root's separate receipt. Root's later finite
GPU receipt and its Windows-only offline audit are documented in the result
report; no NPU or live engine cohort was executed by this component.

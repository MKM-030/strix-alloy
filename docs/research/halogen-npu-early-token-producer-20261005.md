# Bounded scheduled early embedding-input producer

`scripts/benchmarks/halogen_mtp_early_token_producer.py` implements an offline,
request-scoped producer driven by the unchanged sealed host-token scheduler.
It starts from original v2 embedding rows, applies the unchanged Q4C decoder,
BF16 RNE, raw embedding gamma and canonical whole-row RMS, and freshly splits
each normalized row for the embedding-only FC component. It reads no FC weight
or hidden payload and performs no FC, provider, device, server or live-hook work.
The current stock server stays open.

The source has standard-library imports at module scope. Metadata planning
loads only the pure scheduler and reads four ordinary frozen JSON receipts.
Numerical imports and checkpoint windows are behind root-owned `--produce`.
This subagent performed Python AST and source whitespace checks only; it did
not execute planning, payload preparation, providers or hardware.

ROOT subsequently executed metadata planning under the owned 22/18-GiB guard
for an explicitly offline verification schedule selecting token14367. It exited
0, all owned jobs closed and the guard stopped. Plan SHA256 is
`0a388aa22ccccfbe8cbdd17ef7e350f04b391cb9085f423ce851d7d5f503261d`, at
`server/.local/optimization9h-20261004/early-producer-plan-147d2f09a2b7404fb4bcd2c1f7f2a33d.json`.
The sibling directory retains `result.json`. Planning read zero payload bytes;
the plan requests 6,624 checkpoint bytes per pass and 47,588 candidate bytes.
Minimum physical/commit headroom was 27.168678/119.807262 GiB. This is a planning
proof for a synthetic schedule, not a live generation binding or executed
checkpoint production. The GPU/NPU component and live-publication gates below
retain their separate scopes.

## Schedule and bounded lifetime

The schedule JSON is the exact `schedule_document(plan)` representation of an
existing `EarlyTokenPlan`: schema `halogen0162.early-token-schedule.v1`, lowercase
nonzero 16-byte `generation_hex`, `sequence`, `path`, `start_position`, copied
`input_tokens`, and `next_token`. The original scheduler validates all token,
position and generation bounds. Automatic schedules use the shifted input
prefix plus a known next token. Verification schedules use known draft tokens;
acceptance and the correction remain unknown.

The producer selects the first 64 stable deduplicated known token IDs. Further
known tokens are explicitly retained as `deferred_known_tokens`. Every row is
a separate count1 input; this does not qualify skipping a native multirow FC.
Unknown correction/tail and deferred tokens require the original path.
`--produce` requires an explicitly matching current generation and sequence,
and rejects a stale request wholesale. There is no persistent cache, upload,
event, device publication or live model-generation proof. `complete.json` is
written last and denotes completed candidate files only.

## Payload bounds and ABI

For a nonempty request, source windows are the original 64-byte codebook,
1280-byte codes and 160-byte scales per selected token, and 5120-byte original
raw BF16 embedding gamma. The exact frozen Linux size/device/inode/mtime/ctime
identity must hold on both checkpoint pathname and open handle. Symlink final
components are refused. Each selected window is reread for exact equality;
maximum checkpoint reads are 97,344 bytes per pass and 194,688 bytes total.
No whole checkpoint or external weight data is hashed or decoded.

The frozen decoder receives a bounded in-memory stream that exposes only the
captured windows at their original checkpoint offsets. Original tensor
metadata stays unchanged. Codebook and gamma have independent frozen hashes;
token14367 additionally has pinned codes/scales and decoded/raw/normalized
fixture hashes. Newly requested rows have observed hashes and strict checkpoint
identity, but still require independent original native arithmetic proof.

Each token emits:

- raw and normalized BF16 words, each 5120 bytes;
- `e_norm` little-endian FLOAT `[1,2560]`, finite and exactly BF16-widened;
- fresh `e_high` and `e_low` little-endian FLOAT `[1,2560]`, from unchanged
  `stable.split_operand(e_norm, -1, np)` and its diagnostics.

`tokens.i32`, `raw-gamma.u16` and a rebased private `selected-rows.q4c` fixture
are emitted for a nonempty request. The Q4C fixture follows stable token order,
with 64-byte codebook, all row codes, then all row scales, stride160. It is input
for a future native multirow oracle, and proves no original full-table loader
or live gather allocation. Maximum candidate payload output is 2,719,040 bytes,
under the fixed 3 MiB budget. Empty known-token schedules read no payload and
import no numerical library.

## Gates retained

All gates stay false in both metadata and candidate receipts:

- original native Q4C/raw BF16 multirow parity and original native embedding
  RMS on every new raw row;
- original full-table or live-allocation provenance for the intended integration;
- embedding-only FC CPU comparison with original native output at unchanged
  `rtol=.002, atol=.0002`, followed by all-output NPU comparison at unchanged
  `rtol=.03, atol=.003` and actual STX hardware proof with CPU fallback disabled;
- same generation, sequence, token and position plus completed upload/event,
  publication lifetime, stale invalidation and correction fallback;
- separate native batch FC skip qualification when actual head count exceeds one;
- supported Windows fabric-clock control and observed held state before any
  concurrent GPU/NPU inference;
- full-engine tok/s A/B, unchanged acceptance and all helper costs.

Mathematical early-input eligibility is separate from overlap admission.
`HALOGEN_NPU_WITH_GPU=1` is explicitly unaccepted as an unsupported workaround.
Until fabric state/control is proven, the embedding-only NPU component may run
only in an owned idle window. The producer admits no native FC skip, useful
overlap, full-engine integration, acceptance or speed claim.

## Root execution prerequisites and CLI

The root reviews and supplies the producer SHA, scheduler JSON SHA and plan SHA.
All four byte-pinned JSON files must be in `--assets`: `embedding-row.json`,
`embedding-row.plan.json`, `weights.json`, `weights.plan.json`. The pinned
scheduler, Q4C decoder, original builder and stable split source must be beside
the producer. The metadata JSON may be copied byte-for-byte to Linux; embedded
Windows prepared-data paths are metadata only and are never opened.

Metadata preparation on Windows, after the root saves the exact scheduler JSON:

```powershell
python C:\Projects\strix-alloy-clean\scripts\benchmarks\halogen_mtp_early_token_producer.py --prepare-only --source-sha256 REVIEWED_PRODUCER_SHA --assets C:\AI\halogen-mtp-npu\v2-d-prepare-20261004 --schedule ABSOLUTE_SCHEDULE_JSON --schedule-sha256 SCHEDULE_SHA --plan ABSOLUTE_NEW_PLAN_JSON
```

Root-only Linux numerical production requires the original native checkpoint
identity, NumPy2.5.3 and the unchanged builder's ONNX import dependencies. All
three numerical thread variables must equal `1` before Python starts. The
output parent must exist and the requested output directory must be fresh:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python3 /ABSOLUTE/SOURCES/halogen_mtp_early_token_producer.py --produce --source-sha256 REVIEWED_PRODUCER_SHA --assets /ABSOLUTE/SEALED_JSON --plan /ABSOLUTE/PLAN_JSON --plan-sha256 PLAN_SHA --generation-hex CURRENT_SCHEDULE_GENERATION_HEX --sequence CURRENT_SCHEDULE_SEQUENCE --checkpoint /home/revn/halogen-models-native/qwen38-flash-next-v2.hgn --out /ABSOLUTE/FRESH_CANDIDATE_DIRECTORY
```

Production above is CPU input preparation only. It neither invokes the
embedding-only NPU component nor observes the live target-entry seam. Root must
protect the existing 18 GiB physical/commit reserve and owns every numerical,
payload, runtime and later hardware operation. Real tok/s gain requires the
full-engine A/B gate; no producer file or local component time supplies it.

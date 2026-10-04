# Halogen 0.16.2 full MTP head: residual and state ABI

The complete MTP head has a concrete four-stream residual input, token/position input, and persistent head history. This map is an integration seam for a future NPU draft; it does not establish cache ownership or rollback correctness.

## Binary pin and provenance

- Engine: `backends/halogen-wsl2-0.16.2/.local/flash_serve` (WSL retained copy `/home/revn/halogen-re/flash_serve0162`).
- SHA-256: `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`; size 26,052,768 bytes.
- Full head forward: RVA `0x17db310..0x17dc289`; function SHA-256 `132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20`.
- RVAs below are from the stripped host ELF; `.text` VA minus file offset is `0x1000`. Role descriptions are inferred from instructions and registered kernel signatures, not exported function names.
- Source-only evidence: retained `server/.local/optimization9h-20261004/mtp-route-static-20261004/{host-text-disassembly.txt,host-frames.txt,kernel-registrations.json}` and `scripts/benchmarks/halogen0162_mtp_tap.c`. No capture, compilation, model/checkpoint read, provider change, or hardware action was performed for this map. The current full-event tap remains unchanged.

`*(model+offset)` means a pointer stored in a host object; the pointed-to tensor is on the device. Widths marked raw u16 establish storage, not a decoded numeric format.

## Residual, token, and position seam

The observed ABI of `0x17db310` is `int32_t(model, const int32_t *tokens, int32_t count, int32_t position)`.

| Input/state | Host field and device extent | Width/use evidence |
|---|---|---|
| Four-stream target residual | `*(model+0x6d0)`; 20,480 bytes/token (`0x5000`), `4 x 2560` raw u16 | Target forward publishes its last row from `+0x6d0 + (count-1)*0x5000`; copy at `0x17ddf68`. This is distinct from the 5120-byte MLP input at `*(model+0x6e8)`. |
| Accepted residual snapshot | `*(model+0x50)`; 20,480 bytes; `int32 model+0x58` position tag | Target forward `0x17dd020` runs layers 0..47, then D2D-copies the last residual row to `+0x50` and tags it from `model+0x220` (`0x17ddf32..0x17ddf7b`). Helper `0x17dc990` publishes the same seam. |
| Head residual continuation | `int32 model+0x5c` produced row count | For offset >0 with at least two produced rows, wrapper `0x17dcde0` copies the last head-produced residual row into row zero (`0x17dce51`). |
| Token IDs | ABI host `int32[count]` -> host staging `*(model+0x6b0)` -> device `*(model+0x730)` | Host copy `0x17db364`; H2D copy `0x17db382`, exactly `count*4` bytes on stream 0. |
| Token embedding | Table `*(model+0x4f0)` -> `*(model+0x6c8)`; 5120 bytes/token, 2560 raw u16 | Registered `k_embed_gather` identity `0x18d5b40`, launch `0x17db449`. Embedding projection descriptor `model+0x908` maps `+0x6c8` -> `+0xb00`, dimensions 2560 x2560 (`0x17db543`). |
| Residual/embedding preparation | Norm pointers `*(model+0xae8)` and `*(model+0xaf0)`; residual projection descriptor `model+0x980` | Full forward normalizes/projects the embedding and incoming residual, then seeds/adds into `+0x6d0` before layer48. Globals `0x18db210/228/230` are transient scratch, not independent persistent inputs. |
| Position | ABI `int32 position`; current position `int32 model+0x220` | Original position saved at `0x17dbb9a`, ABI position installed at `0x17dbbad`, restored at `0x17dbbe6`. Wrapper supplies `model+0x220 + offset - 1` (`0x17dcf44`). |

The wrapper restores snapshot `+0x50` -> residual `+0x6d0` at `0x17dcf23` when the snapshot tag matches the current position. Accepted-prefix helper `0x17def00` sets `model+0x220 = model+0x1c + accepted_count`, copies residual row `accepted_count-1` to the snapshot at `0x17def6e`, and retags it at `0x17def81`. Snapshot publication is conditional on MTP being enabled and native speculative/multislot path flags; it is not an unconditional end-of-forward contract.

## Layer48 history

Let `T = *(model+0x4d8)` and `L48 = T + 48*0xc68 = T+0x25380`. Dispatcher `0x17d9eb0` reads the byte `L48[0]`: kind 1 calls attention/indexer `0x179df80` (`0x17da135`); otherwise it calls DeltaNet/conv/recurrent `0x1791030` (`0x17da148`). Runtime layer48 kind has not been observed. Allocation explicitly provisions layer48 K/V when `model+0x900` enables MTP, which supports but does not replace that observation.

| Attention/indexer state | Device pointer field | Proven extent and publication |
|---|---|---|
| K history | `*(L48+0xb98)` = `*(T+0x25f18)` | Contiguous row: 1024 bytes =512 raw u16. Destination adds `position<<10`, copy uses `count<<10` (`0x17a0b90..0x17a0bbb`). Allocation capacity is `int32 model+0x21c *1024` bytes (`0x176ed71..0x176ed8d`). |
| V history | `*(L48+0xba0)` = `*(T+0x25f20)` | Same 1024-byte row; publication `0x17a0bcb..0x17a0bee`; same capacity (`0x176ed95..0x176edad`). |
| Compressed indexer keys | `*(L48+0x4f8)` = `*(T+0x25878)` | 256 bytes =128 raw u16 per pooled row (`0x179ba34`); `k_block_pool` publishes at `0x179bafa`, positions grouped by4. Total pooled-row capacity unresolved. |
| Indexer carry | `*(L48+0x500)` = `*(T+0x25880)` | Exactly 768 raw bytes: allocation `0x176eddc..0x176ede1`, native save/restore copies `0x300` bytes. Interpretation as three leftover key rows remains inferred. |
| Carry snapshot | `*(model+0x68)`; position tag `int32 +0x70`, slot tag `int32 +0x74` | Current carry -> snapshot at `0x17dca56`; snapshot -> current carry at `0x17dcaec`, then invalidates position tag. Save keys against `model+0x220` and `model+0xa0`. |

These histories are produced by preceding head attention/indexer work; the target-layer residual publication does not copy them. The 768-byte carry snapshot does not cover K/V or compressed-key history. If runtime kind is not 1, `*(L48+0xb88/b90)` (absolute `T+0x25f08/25f10`) are the alternative conv/recurrent state inputs; their live extents and lifecycle remain unresolved for this seam.

## Ownership and rollback gap

The contiguous K/V map is not universal. At `0x17a0935`, `byte model+0xa4 ==1` selects `k_kv_scatter_rows` with a by-value `FdRows` descriptor; other paths also read owner metadata through `*(model+0x108)` and use slot indirection. A raw K/V pointer does not prove which rows a draft owns.

Accepted-prefix rollback `0x17def00` iterates only target layers 0..47 and swaps saved conv/recurrent/indexer pointers. Layer48 history commit/discard and FD slot lifetime have not been established. A future draft must isolate mutable head state and define how an accepted prefix commits it and a rejected suffix discards it. An approximate NPU draft may emit token IDs for native target verification without matching internal MLP FP32 exactly; that does not remove the state/position/rollback contract. No performance claim follows from this map.

## Future metadata-only observation (not implemented)

Use a separately reviewed observer version in a future owned full-head run. At the full-forward entry, save one bounded host-only record containing ABI count/position, `byte L48[0]`, `byte model+0xa4`, `int32 model+0xa0`, `int32 model+0x220`, and pointer presence/values for `model+0x108` and the four head history fields. Validate the host layer table contains descriptor48 before reading it. This directly answers runtime kind and the scatter-mode flag without copying tensor payloads.

For active FD metadata, within the full-forward TLS scope record the native kernel identity. `k_kv_scatter_rows` is `base+0x18d5338`; FD attention identities are `base+0x18d5348/0x18d5350`. The scatter launch constructs its third argument as a **160-byte host `FdRows` object** (`rsp+0x290..0x32f`, construction `0x17a09b0..0x17a0aff`, argument address `0x17a0b06..0x17a0b0e`). A future `hipLaunchKernel` observer can copy only this fixed-size host argument from `args[2]` into a preallocated record, once per selected count1 call, before forwarding the original launch. Retain it as raw metadata; never follow its device pointers. Bound observation to a few calls, flush records after timing, and add no HIP copy, synchronization, or native-state write. Label this separately instrumented run and its observer overhead. Absence of an FD kernel must be reported with the entry flag and observed kind, not treated alone as proof of contiguous ownership.

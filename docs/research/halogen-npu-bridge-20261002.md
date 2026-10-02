# Halogen NPU bridge investigation — 2026-10-02

## Implemented

- `halogen_npu_scheduler.py`: isolated FLM NPU sidecar supervisor.
- `halogen_npu_ab.py`: control/concurrent/control qualification; concurrent NPU work fails closed above 1% Halogen decode regression.
- `halogen_npu_seam.py`: inventories binary state-export/tap capabilities.
- `halogen_mtp_extract.py`: extracts the 31 embedded `mtp.*` tensors from a Halogen HGN into a standalone HGN without re-quantization. A synthetic regression test verifies table/payload selection. The real w4b extraction produced 31 tensors / 1,479,351,552 bytes and metadata matches the source entries.

## Current Halogen 0.15.1 binary

The pinned `flash_serve` SHA-256 is `81a5f68fe418358b8684cdd520651fa14217d586409fcc1a0e8a81bb5e3ec4af`.

Static xref/capability inspection shows:

- `HALOGEN_MTP_PREFILL` is compiled in and defaults enabled when unset. Setting it is not a new optimization.
- `HALOGEN_TAP_FROM_SCAN` is compiled in and defaults enabled when unset. It selects an internal tap source; it is not an external IPC/export endpoint.
- The older Halogen engine binary contains `--drafter-taps`, `--drafter-hidden`, `--drafter-ingest-bench`, `--drafter-round-bench` and `drafter.target_hidden`; current 0.15.1 `flash_serve` does not expose those CLI export flags.
- Therefore an online NPU MTP bridge still requires a new Halogen state-export/import seam or upstream/source support.

## FastFlowLM finding

FLM 1.0.7 ships `qwen3_8mtp_npu.dll` and `xclbins/Qwen3.8-27B-NPU2/MTP_layer.xclbin`. Binary inspection confirms an actual NPU MTP implementation (`npu_mtp_layer`, `speculate_npu`, `MTP_layer.xclbin`) and exported timing/statistics methods. The public header comments are stale/incomplete relative to the shipped DLL: the DLL explicitly states there is no host fallback and the decoder/MTP path runs on-device.

This NPU kernel cannot be dropped into Flash-Next unchanged. Qwen3.8-27B uses hidden size 5120 / intermediate 17408, whereas Flash-Next's Halogen MTP tensors use 2560 base width, four-stream 10240 hyperconnection state and a 512-expert MoE MTP layer. The xclbin/runtime ABI therefore needs a Flash-Next-specific layout/weight staging path.

## Decode decision

The useful target remains `Halogen target -> normalized target hidden -> NPU Flash-Next MTP -> Halogen verify`. A whole second NPU model is not the drafter. Prior coexistence measurements already showed continuous independent NPU work reduces GPU decode by roughly 7%; idle/throttled sidecar work is a system-throughput feature, not a Halogen tok/s speedup.

Next implementation boundary is a Flash-Next-specific NPU MTP layer using the extracted 31 tensors. The FLM DLL exports low-level `npu_mtp_layer`, `mtp_layout`, `mtp_proj` and NPU sequence symbols, but its packaged xclbin geometry is for 27B. Reusing that ABI without a matching Flash-Next xclbin would be unsafe.

## Prefill decision

NPU-prefilling an independent model cannot accelerate Halogen because its KV/DeltaNet state is not interchangeable. Halogen's own `HALOGEN_MTP_PREFILL` is already enabled. A useful NPU prefill split needs a contiguous Flash-Next subgraph plus state import/export; until that seam exists, the qualified GPU prefill tuning remains the correct path.

## Additional measurements and binary inspection

FLM 1.0.7 NPU validation on this BOSGAME reports `amd_device_found=true`, `npu_driver_ok=true`, `ready=true`. A local Qwen3-0.6B-NPU2 sanity run at a 574-token prompt measured 1001–1022 prefill tok/s and 92.2–93.0 decode tok/s (three requests; generated lengths 72/128/73). This is only an NPU health/throughput probe, not a Flash-Next speed claim.

The shipped `qwen3_8mtp_npu.dll` exports the low-level `npu_mtp_layer`, `mtp_proj`, `speculate_npu`, `mtp_draft`, state save/restore/crop, and speculation timing/statistics symbols. Its packaged `MTP_layer.xclbin` is therefore a genuine NPU MTP kernel, not merely a CPU implementation. The public v1.0.7 header comment describing a CPU-only phase is stale/incomplete relative to the distributed binary.

`halogen_npu_compat.py` now fails closed when comparing the extracted Flash-Next head to the packaged Qwen3.8-27B kernel geometry. Flash Next uses 2560-wide MTP projections, 10240-wide four-stream hyperconnection state and a 512-expert MoE (`experts.gate_up_proj` shape 512x1280x2560). Qwen3.8-27B uses hidden size 5120 and a dense MTP. Result: the packaged 27B `MTP_layer.xclbin` is not a safe drop-in kernel; a Flash-Next-specific xclbin/layout is required.

A fresh current-Halogen A/B run was attempted after the old local worktree was intentionally removed. The ignored local v2 HGN had not been retained in Git. The remaining 124.1-GB w4b checkpoint can be mapped directly from NTFS, but with the current 64-GB Windows GPU carve-out Halogen correctly refuses to pin its 65.60-GiB trunk: only ~53.5 GiB was available and the 16-GiB floor would be violated. No unsafe memory-floor reduction was attempted. Prior completed v2 coexistence evidence remains the valid current result: continuous independent NPU load costs about 7% GPU decode; throttled work reduced the loss to roughly 2–3% but did not accelerate Halogen.

## Concrete next engineering step

The next speed-producing implementation is not another sidecar flag. It is a Flash-Next-specific NPU MTP xclbin/sequence with this contract: 2560/10240 target-hidden input, hyperconnection mixer, Flash-Next attention, 512-expert top-10 MoE, and the draft readout. Halogen 0.15.1 has internal tap machinery (`HALOGEN_TAP_FROM_SCAN`) but no external online tap/import API. Therefore the second required change is an upstream/source-level Halogen hook that exports normalized target hidden state and accepts NPU draft tokens while retaining Halogen target verification and rollback. Prefill NPU work has the same state-boundary requirement and is not promoted independently.

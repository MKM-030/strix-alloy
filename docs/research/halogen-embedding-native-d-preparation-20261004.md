# Original embedding RMS and composed D graph: CPU preparation

Four root-owned CPU windows completed with retained jobs, source seals and the
22-GiB admission / 18-GiB runtime reserve. They created frozen embedding RMS
fixtures, compiled the original embedding RMS host replay, read the exact
native FC function and verified the Windows capture fix, and built the composed
D algebra graph. All children exited successfully, their jobs closed, monitors
stopped, and stderr was empty. This does not qualify GPU/NPU arithmetic or a
speed improvement. The live user engine was preserved.

| Window | Minimum physical / commit headroom, GiB |
|---|---:|
| Embedding fixtures | 25.400 / 117.387 |
| Host GCC compile and binary hash | 25.469 / 117.446 |
| Native dispatcher and Windows capture read | 25.485 / 117.465 |
| Composed D protobuf build | 25.436 / 117.448 |

The [retained preparation evidence](halogen-embedding-native-d-preparation-20261004.json)
binds the complete owned-job results, source hashes and original artifacts.
The successful embedding fixture manifest has SHA256
`cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246`.
Its unchanged raw gamma is 5120 bytes, SHA256
`04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86`.
The frozen A/B raw inputs and NumPy/retained ORT references are recorded
separately; no provider or inference session was created to prepare them.

The earlier failed fixture attempt is preserved. Python 3.12 Windows path stat
and open-handle stat reported different `st_ctime_ns` for the same unchanged
file, while birth time, device, inode, size, modification time and selected-byte
hash matched. The fix compares birth time across these APIs and retains ctime
stability checks separately within each API. POSIX still compares ctime across
APIs. This follows Python's documented Windows [birth-time semantics](https://docs.python.org/3.12/library/os.html#os.stat_result).
The corrected `halogen0162_fc_owned_run.capture()` then successfully captured
and hashed the actual 5120-byte gamma file under the retained owned CPU job.

The compiled original embedding RMS replay is
`/home/revn/halogen-re/embedding-rms-replay-9b772ea1c64141039885b462700f091a`,
SHA256 `22d7159d69d4a8ca6753be7bef60773dae2015ed206c435e1f9f270594b1d6d2`.
GCC used `-O2 -Wall -Wextra -Werror`; the binary was hashed in a second owned
CPU stage and never executed. Its separate image wrapper and owned controller
preserve the original shader, aliased X/Y, raw gamma, two calls, exact runtime
and input seals, failure retention, and cleanup. They refuse a live user engine.
Source self-review and root peer review found no concrete defect; hardware
qualification remains pending.

The native ELF read independently verified the complete engine hash, unchanged
file identity, unique executable PT_LOAD mappings and the previously pinned
head function. The FC dispatcher at RVA `0x178cf90..0x178efa7` maps to file
offset `0x178bf90`, spans 8215 bytes and has SHA256
`f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9`.
This supplies the missing exact-version pin for the
[paired projection integration seam](halogen-mtp-d-projection-integration-20261004.md).
No native function was called by that read.

The composed D graph has model SHA256
`0f3da669a0ff20473dd6c3565081a367e61305cfb34d5fab021ef274574488f5`.
It preserves all original external initializer bytes, BF16 weight casts,
projection BF16 boundaries and seed-add nodes, and emits a flat `[1,10240]`
seed plus diagnostics. Its fixed256 RMS reduction changes FP32 reduction
order. Native RMS, Q8 decoding/DOT2 accumulation, full-D/head parity, NPU
placement, acceptance and speed qualification remain false. The graph was
checked and serialized without a provider session.

The next exclusive hardware window must run native embedding RMS first. If
its normalized words differ from the existing FC fixtures, retain those
fixtures and create a new native-input lineage. Then run the original FC
oracle, frozen CPU projection gates and NPU gates. Paired publication and
accepted-prefix lifecycle qualification remain necessary before any offload
or end-to-end speed claim.

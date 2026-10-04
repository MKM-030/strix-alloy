# Official offline QMoE packing at Halogen geometry

The root-owned AMD Dynamic Dispatch 1.8.0 offline packing invocation passed
for both Halogen expert matrices. This is a construction prerequisite, not
NPU inference, accepted drafting, residency or a throughput improvement.

| Matrix | Logical K/N | Returned padded K/N | Packed bytes |
|---|---|---|---:|
| Gate/up FC1 | 2560/1280 | 2560/2560 | 4,198,400 |
| Down FC2 | 640/2560 | 768/3072 | 1,597,440 |

The source [construction contract](halogen-npu-light-qmoe-contract-20261004.md)
requires a 65536-byte expert stride. FC1 followed by FC2 therefore needs
36,864 tail bytes, giving a 5,832,704-byte stride. Its FC2 graph attribute must
include that tail: 1,634,304 bytes. A streamed synthetic 512-expert bank is
2,986,344,448 bytes (2.78125 GiB), SHA256
`05283a60ce7858fdfa93d46ce84e86a5a38d5bbe46631e8571d2ff632890365f`.
The complete bank was never materialized as one NumPy array. All experts are
synthetic zero weights, so the bank can qualify only provider admission.

The complete official wheel was downloaded and verified against AMD's
advertised SHA256
`8988620998c23a0d1a71bf2ced9a5287bc6641133ad38b67900fa4c546e7a8e4`.
The extension SHA256 is
`38814ad69d2233758b76bf82db922f2e674c0d01aace756ace066135cbf4aaab`.
Loaded `xrt_coreutil.dll` was explicitly checked against the reviewed installed
DriverStore path and SHA256
`04a26d37c6e0c713491ad0bfae74ce74ea94c74136d2aa056333616dac6c3a44`.
No package, driver, firmware or global environment was installed or changed.

Both guarded children exited zero and their owned jobs closed. Their parent
guards enforced the unchanged 18-GiB physical/commit floor and confirmed
terminal GPU state throughout. The bank invocation observed minima of
49,186,607,104 available bytes and 217,838,759,936 commit-headroom bytes.
Packing times are host construction measurements; they are not NPU latency.

Artifacts remain ignored under
`server/.local/optimization9h-20261004/qmoe-pack-admission-59d44a22c36f4331a5ace7a9c480c7c0`
and `qmoe-pack-admission-5306a9a57ecd44d79255fce2cc89378b`.
Each directory contains child packing and parent lifecycle receipts, source
pins, memory observations, stdout and stderr. No failure evidence was replaced.

The bounded CPU affine converter passed its single numerical fixture. It
reconstructs q4c weights before approximate affine INT4 quantization and makes
gate/up row ordering explicit. Its diagnostics exclude the official packer's
BF16 scale rounding and NPU arithmetic. Live draft quality still requires
native target verification; internal exact FP32 parity is not the acceptance
requirement. Full NPU MTP remains incomplete.

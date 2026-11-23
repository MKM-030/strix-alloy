# Halogen 0.20.7 launch-time profiling and nested prefill

The pinned 0.20.7 container completed a small GPU fixture on the Radeon
8060S under WSL2. ROCprofiler-SDK 1.4.1 recorded two HIP launch calls and
four HIP copy calls in the fixture's process. It emitted neither a kernel
dispatch trace nor a memory-copy trace. The calls establish that the process
submitted work and waited for its results. GPU execution intervals and
Windows Copy engine ownership remain unmeasured.

## Profiling fixture

The fixture checked 524,288 output words against its CPU expectations. Each
of two named kernels operated on a 1 MiB device buffer, with one blocking
copy in each direction. The container checked the pinned HIP, HSA, DXG and
Windows DXCore library hashes before launch. Both attempts ended and their
containers were removed automatically.

The first attempt reached the profiler's output stage and aborted when the
profiler tried to create `.rocprofv3` under its read-only working directory.
The second changed the working directory to a private writable `/tmp` and
completed the fixture. The capture verifier rejected the missing dispatch
and copy reports. The reported GPU agent had the correct adapter name but
zero CU, SIMD and gfx target fields. The lowest sampled physical or commit
reserve in the second attempt was 30.48 GiB.

AMD documents dispatch and copy collection with an experimental WSL2
profiler and a matched runtime and DXG thunk. The local result applies to
the profiler and libraries shipped in this Halogen image. The successful
HIP API capture leaves the runtime cause of the missing GPU reports open.
[AMD's WSL2 profiling guide](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/develop/how-to/using-rocprofv3-on-wsl.html)

## Nested prefill

The first arm ran four pairs of 16,384- and 1,536-token requests. Docker's
UTC offset relative to Windows shifted by about 132 seconds during that arm.
The clock-order check rejected the cohort and the 2,048-token admission
candidate never ran. The comparison changes when the short request can
start while the long prompt is processing. It cannot establish a
single-request Decode improvement.

The campaign restored the normal 32K, single-slot Halogen 0.20.7 server on
port 8840. Authenticated gateway and backend health, ServiceNow routing,
Native Voice, TTS and ASR all passed. The fixture used a separate container
without a model or service mounts and left that server available.

## Local evidence

The run files are under
`server/.local/halogen-update-20261122/primary0207`. The nested campaign
retains its four pairs and clock probes alongside its terminal handle.

| Evidence | SHA-256 |
| --- | --- |
| Profiled fixture console | `a9984c435bf8ceb5698214fc26dc5fbc5fd7c34c7626bea1208e11dfc192776d` |
| Fixture HIP API trace | `222925c78532601becd8498d97f48c8cad45a33a043f6acf5a389c8e6c19d5c4` |
| Fixture GPU agent report | `ea9dcbb092d37115d7711666551fdc90ff3afcd33a724f52260dfb49e4670455` |
| Fixture terminal receipt | `c0628fc3ca1e046c5d6ed1e7658f880d8caf975edc4b2c500fdeb716c02ede32` |
| Nested campaign terminal handle | `257723b7462e60d17bfcf26f736dff46fec55ecf021b2647a95ee98c0e2e3971` |
| Restored services | `ef5f13798599449a1717dd6ccc95124aec0bc73bb5d880e44b916dc6d1515a2d` |

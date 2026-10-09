# Device-predication evidence sources

These byte-identical text snapshots support the [component result](../halogen-gpu-device-predication-20261009.md). The candidate failed its frozen performance admission and remains disabled. They are an experimental owned-buffer harness and CPU/device predicates; they contain no live engine hook.

The sibling directory layout preserves the measured local include chain:

```text
bn64-device-predication-20261009/component-host.c
  -> oracle.c
    -> predication.hip
    -> ../bn64-device-validation-20261009/oracle.c
      -> validator.hip
```

The two validation files are the recorded CPU-oracle dependencies. All five source sizes and SHA256 bindings are in the [JSON summary](../halogen-gpu-device-predication-20261009.json). Native kernel symbol names and object hashes are ABI/fingerprint metadata. Synthetic operand generators are retained; no model weights, prompts, generated answers or credentials are included.

Hardware mode depends on separately supplied pinned native/custom code objects, a HIP library and the custom object's SHA256. HIP headers are needed for device compilation; the host uses POSIX headers, libdl and dynamically resolved `libcrypto.so.3`. Vendor/native binaries, compiled outputs, disassembly, local lifecycle controls and large stdout receipts are omitted. This archive is not a serving installation or integration instruction.

The compact JSON retains all 36 measured and six warmup timing tuples, derived host/GPU metrics, position groups, all 41 correctness-case identities/statuses, build/control summaries and hashes of unchanged local receipts. Raw evidence remains in the local experiment directory; it was not rewritten for publication. Preparation/mock results and actual GPU correctness are distinguished. The original pending-restoration snapshot is preserved, and the subsequent root-owned ready/open restoration receipts are bound separately.

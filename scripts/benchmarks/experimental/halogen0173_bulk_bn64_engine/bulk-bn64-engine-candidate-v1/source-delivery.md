# Source delivery receipt

Delivered 2026-10-09 from the prefill new-mechanism scope. All authored artifacts are confined to this candidate directory. Root owns migration, builds, GPU/NPU hardware, engine lifecycle, output/performance comparison, STATE and Git.

- `adapter.c`: default-off, pinned native BN64 LD_PRELOAD candidate.
- Settled source SHA256: `1168a01f8ffd7346f6b63144b4b1f28e8801c15bc84ecaa56c5364961dba7da7`.
- `host-map.json`: machine-readable 0.17.3 descriptor/registration/launch map, ABI and 446464-byte allocation budget. JSON parse and source-hash consistency checked.
- `host-0173.txt`: inert host disassembly used for the mapping review.
- `independent-abi-transaction-review.md`: independent bounded review receipt; no outstanding ABI, capacity or launch-transaction finding in the settled snapshot.
- `README.md`: scope, rollback behavior, build and activation instructions.

The last source delta changes only the missing-native-symbol diagnostic: `write()`'s return value is stored in `ssize_t written` and explicitly discarded before the existing `_exit(127)`. Root requested this GCC `-Werror` portability repair after its first compile attempt. The adapter behavior and all pins are unchanged.

This scope did not compile or execute the adapter and prepared no mock fixtures. No engine output equality, net engine gain, acceptance or serving qualification is asserted. Component evidence and source review justify handing the bounded candidate to root for those checks. Source is frozen for root's build/run unless a material defect is found.

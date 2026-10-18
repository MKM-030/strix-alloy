# Strix Alloy worktree consolidation, 18 October 2026

All five discovered development histories were checkpointed and integrated into `main`, including the source files that were dirty or untracked at the initial inventory. The later six-file portable Voice change was preserved in commit `198ea7f46b700fa80902f3b816a8ee45d404acec` and merged in `a77b973130cccc0d68153e79f0b83b7ba996e481`.

| Development tree | Preserved checkpoint | Disposition |
| --- | --- | --- |
| Primary | `47ef9de41a58b736ef5efbba3772ecb7cd424896` | Main working directory |
| Research integration | `2af656f7f0e5ab012bc525bc4ba2bc6da5fe9632` | Integrated; old checkout removed |
| NPU ready embedding | `1a82e0f424640cd614cce255b4b3b3fa56e7c707` | Integrated; old checkout removed |
| GPU draft snapshot | `abb17652deede6d247a721c8c11d26ad94ade8a9` | Integrated; old checkout removed |
| SCC Voice | `3b37a7da32d8585f5cc304674bcdc128086e8c9b`, then `198ea7f` | Integrated; old checkout retained for active programs |

Resolution kept the current primary lifecycle/controller fixes while incorporating the NPU and research work. The historical alternatives remain in Git history and do not become enabled optimizations merely because their source is integrated. No model, driver, firmware, BIOS, voltage or global WSL setting was removed or changed by consolidation.

Private Voice dependencies and stable assets were copied and verified in the primary directory. Volatile runtime records were retained as historical snapshots. All ten discovered desktop/startup shortcuts now point to the primary tree. The private Voice config received the previous explicit instance origin so the newly portable source preserves its existing destination on a later restart; credentials and ACLs were preserved.

The old `strix-alloy-scc-voice` directory still supports live native-bridge, Studio, Bot and gateway processes. Those programs were not terminated. Its source history is merged, but its on-disk removal remains outstanding; no net disk-space saving is claimed while those dependencies coexist. A generated native test kernel cache was retained under the ignored `backends/hipfire-windows/.local` directory after automatic approval review rejected recursive deletion.

Targeted validation after the final Voice merge: 39 bridge/settings tests and 8 native bridge context/end tests passed. The [new native Hipfire report](../benchmarks/hipfire-native-windows-20261018.md) records its separate release build, full-model cohort, HTTP smoke and performance limits. The normal Halogen 0.18.8 serving instance is restored afterward on port 8840.

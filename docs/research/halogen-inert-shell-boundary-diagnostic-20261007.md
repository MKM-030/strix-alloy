# Inert shell boundary diagnostic — 2026-10-07

The single bounded CPU diagnostic passed with strict equality between the background golden observer and the sourced wrapped background observer. Their complete raw environments matched, and their complete environments after the existing `_` restoration matched. The foreground observer differed from each background observer only at `SHLVL`; no keys were missing or added. Environment values remain represented by hashes.

The frozen failed test launched its golden vector in the foreground and its candidate in the background. The new diagnostic preserves that foreground observation and adds a background golden from the same Bash parent and scope. All three use the same `python3 -I` observer. The appropriate oracle is the matching background golden, with every environment key and value retained in strict comparison. No `SHLVL` normalization, filtering, or tolerance was added.

The exported receipt hashes and source pins were independently checked offline. The observed shell PID was 7; foreground, background, and wrapped observer PIDs were 8, 9, and 11. Both captured `$!` values matched their observed child PIDs, and every parent binding matched PID 7. Argv and canary hashes matched. The container terminated with exit 0 and no OOM indication.

The old failed attempt remains failed. Its aggregate environment hashes did not identify a key; its frozen receipts, plan, and sources were preserved. The new reproduction establishes the `SHLVL` difference in that foreground/background test topology. It does not retroactively add per-key observations to the historical attempt.

Evidence is retained in `server/.local/optimization9h-20261004/inert-boundary-diagnostic-run-0db773a0261f42e4ac6a7b74782437db/` and summarized in [the tracked evidence](halogen-inert-shell-boundary-diagnostic-20261007.json). Result SHA256: `798566cccc5382b38380c9fbfdc8c3b040844ed69c937ab53a0b8b70dda7e6f3`. Comparison SHA256: `3c6c5235af58925fbb2a29fbe5053c0ab39b609a1672a1532fd967f47b9ae63d`.

The next serving coordinator can validate these successful pinned receipts in place of rerunning the obsolete inert oracle. This is an inert same-Python shell topology result. No engine, native helper, device, NPU integration, serving Copy attribution, throughput, or acceleration was qualified by this diagnostic. Actual bootstrap and post-exec engine identity still require their own owned execution and inspection.

# Halogen 0.17.1 runtime preparation and startup result

The separate 0.17.1 backend is installed. It is not the serving default and has
no qualified runtime, Prefill, Decode, acceptance or NPU acceleration result.
The original 0.16.2 ServiceNow tests were explicitly ended by the user before
normal lifecycle work began. The original profile and credential were retained.

The new image is pinned to
`sha256:1952e5c5a50a6c0c52b748b505cba401ce88f7ce92e6b3c8253b4f5bdbcd3161`
and the engine to
`740c74166147fd933867469467bf125825f99e4e53c8c7dcd8a72709a91400b9`.
All 21 compressed layers, totaling 919,792,612 bytes, were verified. The complete
ordered final overlay contains 15,332 virtual paths, 148 regular HIP headers
and 42 Python package metadata records. The first inventory stopped at the
22-GiB reserve floor; its failure was retained. The identical reviewed source
completed in a separate output directory after engine teardown.

The HIP probe compiled against these final headers. The ordinary installer
reproduced all four expected adapters/probe hashes and completed cleanup of its
stopped setup container. The OCI archive loaded successfully; a normal pull of
the exact repository digest then established its missing repository association.
No model, driver, BIOS, voltage or global WSL configuration was changed.

The canonical backend's 39 source pins and four installed artifact pins passed
independent review. The private 0.17.0/0.17.1 seals and original 0.16.2 sources
were preserved. The reviewed controller/profile change adds explicit support
for canonical 0.17.0 and 0.17.1 paths while retaining 0.16.2 defaults and existing
experiment restrictions.
The existing seven controller checks and four profile-routing checks passed
again after promotion; the live files match the reviewed test mirrors exactly.

The initial 0.16.2 shutdown completed engine cleanup but failed its three-minute
RAM-recovery target. A separate later recovery proof matched the original
process births, empty inference ports, no running containers, and five native
memory samples above the original recovery target. Only the original runner's
exact retained lock was retired; its failure records were not rewritten.

The first fresh baseline start failed before creating an engine or submitting
inference. Although a native pre-WSL watch had passed 40/131 GiB for 60 seconds,
WSL initialization reduced the available physical RAM to 36.7–38.3 GiB.
The baseline attempt ended with `ready=false`, `cleanup=true`, `recovery=true`.
This is an admission failure, not a throughput regression or a valid cohort.
The subsequent reserve check retains one owned WSL sleep process so that
initialization is accounted for before another normal start is considered.

A second baseline attempt also stopped before engine creation. Its normal
cleanup and recovery both completed. WSL had become idle during the Windows
admission wait; after a later WSL initialization, the final check observed
38.46 GiB physical and 191.36 GiB commit headroom. No inference requests were
submitted by either failed start, so neither supplies a rate or acceptance
measurement. A bounded WSL keepalive now accounts for this initialization
through the next admission decision. Current serving state is **stopped**, and
restoring the saved original profile ready/open remains outstanding.

One working-set trim of the verified Codex tool host and one bounded action
on its main/UI processes completed without terminating any program or changing
memory quotas. These are host preparation actions, not engine performance
results. The latest warmed observation recorded 38.63 GiB physical available
and 191.43 GiB commit headroom. The user has been asked to free 2–3 GiB by
closing unneeded applications; no additional lifecycle approval is required.

Startup admission remains 40 GiB physical and 131 GiB commit headroom at
262144 context capacity. Runtime reserves remain 18/18 GiB. The retained
260000-token cohort's 22.56-GiB decline does not support a lower full-context
startup threshold. A successful start does not prove threshold sufficiency
under a later full-context workload.

The pending comparison uses the retained nonrepetitive 8192-token prompt,
128 output tokens, temperature 0, seed 1, Thinking Off, Cache Off, MTP2/PLD3,3,
and explicit prefill chunk/arena 8192/8192. Each window excludes one warmup and
requires three measured samples. The original console profile must be restored
ready and open after the singleton comparison. No defeated NPU cohort is repeated.

Acceptance from the unchanged API/harness must be labelled **API-reconstructed
combined MTP+PLD acceptance**. The API reconstructs accepted head tokens from
commit/round/shared/PLD accounting; it does not expose exact head1/head2 accepted
proposal counters. Tokens committed per round are not an acceptance percentage.

Raw records are retained under
`server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/`,
including the quiescent inventory, runtime probe build, archive, image identity,
canonical promotion, original delayed recovery and final source/install review.
Actual current identities and handles remain authoritative in
`continuation-current.json`. Earlier passive checkpoints must not overwrite the
human-ended test window or claim the stopped original instance is ready.

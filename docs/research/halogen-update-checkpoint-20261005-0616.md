# Official update check — 5 October 2026, 06:16–06:21 UTC

No material release, supported integration or performance change was found
against the 03:50 UTC checkpoint. This was a read-only metadata/documentation
check; no package, setting, model or engine was changed and no inference ran.

Halogen `main` and latest tag `v0.16.2` still resolve to
[`7f31bbd4021f217a1be9776bdb7304bcf8eca62d`](https://github.com/peonist-ai/halogen-flash-server/commit/7f31bbd4021f217a1be9776bdb7304bcf8eca62d),
committed October 3 at 04:29:22 UTC. ROOT's GitHub REST requests confirmed the
main commit, latest tag list and annotated-tag dereference. The latest GitHub
Release endpoint returned 404; this does not negate the published tag.
The pinned [NPU contract](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md)
and [flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md)
still provide no supported replacement-MTP interface or Windows FP11 fabric
hold/readback contract for this host.

| Official channel | Available/current | Other status |
|---|---|---|
| [395 graphics](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html) | Optional 26.9.2 WHQL, September 29 | Recommended 26.8.1 WHQL, August 20 |
| [Ryzen AI software](https://github.com/amd/RyzenAI-SW/releases/tag/v1.8.0) | 1.8.0, July 23 | Official release metadata is not a prerelease |
| [Separate Ryzen AI NPU driver](https://ryzenai.docs.amd.com/en/latest/inst.html) | Production 32.0.203.376 | Minimum 32.0.203.280; distinct from GPU package contents |
| [Windows ML VitisAI](https://github.com/microsoft/WindowsML/wiki/Windows-ML-Execution-Provider-Releases) | MSIX 1.8.75.0 / EP1605 | 1.8.80.0 remains upcoming; not established GA availability |

The [26.9.2 notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html)
still list Driver Store 32.0.32015.2008 and packaged NPU MCDM
32.00.20102.3930. No documented Halogen/WSL speed fix was found. Installed
inventory was not refreshed, and these available channels do not prove
compatibility of a different installed driver.

Focused primary-source searches found no new supported FP11/395 Windows
fabric-hold/readback route. The
[Ryzen Master Monitoring SDK](https://www.amd.com/en/developer/ryzen-master-monitoring-sdk.html)
is read-only; [ROCm 7.14 notes](https://rocm.docs.amd.com/en/docs-7.14.0/about/release-notes.html)
describe MI300A maximum FCLK capping, which does not establish the required
395 Windows top-state hold. This remains a scoped negative finding.

A recent [Reddit discussion](https://www.reddit.com/r/StrixHalo/comments/1wxlxp7/im_a_complete_beginner_with_strix/)
suggests NPU embeddings/reranking, repeating existing separate-service
functionality. No new reproducible same-engine MTP improvement or supported
integration contract was established. This community lead is not independent
proof of a tok/s benefit.

The existing controller/backend process identities were verified live. The
server remained ready/idle, completed5/cancelled0. Physical reserve was
21.218 GiB initially and 21.299 GiB at the final observation, below22 GiB
request admission; commit headroom was above114 GiB. The prepared arena8192
profile checksum still matches and it remains unstarted. No new measurements,
NPU executions, restarts or cache-advice calls were made. Goal status remains
blocked, and the specific colleague-interruption question remains unanswered.

[Structured receipt](halogen-update-checkpoint-20261005-0616.json).
Next official check is due at 08:16:38 UTC.

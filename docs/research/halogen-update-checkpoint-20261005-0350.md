# Official update check — 5 October 2026, 03:50 UTC

Local read-only GitHub REST metadata closes the earlier uncertain main/tag check:
main and latest `v0.16.2` both resolve to `7f31bbd4021f217a1be9776bdb7304bcf8eca62d`
(October 3). No new release or qualified performance change was found.

AMD still lists optional 26.9.2 and recommended 26.8.1. Ryzen AI remains 1.8.0;
its install page identifies minimum NPU driver 32.0.203.280 and production
32.0.203.376. Windows ML lists current VitisAI MSIX 1.8.75.0 / EP1605; 1.8.80.0
is in its upcoming column. These are separate source channels, not installed
driver observations. Nothing was installed.

The current [Halogen flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md)
require the fabric clock held at its top level for supported simultaneous GPU/NPU
execution. Override `HALOGEN_NPU_WITH_GPU=1` bypasses that guard and is unsupported.
GPU/node-frequency getters do not establish fabric-clock identity or a hold.
Current host overlap remains unadmitted; isolated idle NPU diagnostics can
continue under root-owned memory and engine-idle guards.

Reddit search found existing benchmark and sidecar reports, including this
project's own post, but no new reproducible same-engine MTP-head improvement.
Detailed source URLs and outcomes are retained in the [receipt](halogen-update-checkpoint-20261005-0350.json).
Next check is due at 05:50 UTC.

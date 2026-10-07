# Inactive Halogen 0.17.1 source candidate

This separate package is uninstalled. The three CPU adapters were built with
the existing GCC 13.3.0 compiler and have fresh hashes; none was loaded. The
HIP probe has not been built. The running ServiceNow server
continues using the original 0.16.2 instance. No credentials, models or prior
installation state were copied. `profiles/release.json` retains null pins for
the HIP header, HIP probe and stock rocRoller. These missing identities prevent
installation and startup until preparation is complete. The source manifest
seals the current 39 source files; it does not establish runtime compatibility.

The exact 0.17.1 engine/site/function binding and five bridge source files were
reviewed separately. The 276-byte transitive callee's changed body remains
semantically unqualified. All HIP/DXG, model-load, tool-loop and throughput
behavior still requires actual runtime qualification.

The first later comparison uses the preserved sibling `comparison-contract.json`
and `comparison-profile-0171.json`: v2 checkpoint, 262144 context/KV positions,
one slot, prefill chunk and arena 8192, MTP2, PLD3,3 and Cache Off. The original
0.17.0 contract is retained as `reference0170-comparison-contract.json`; successor
identity is bound in the new contract and exact 0.17.1 profile.
Startup 40 GiB physical/131 GiB commit and runtime 18 GiB reserves remain unchanged.

The concrete mechanism to evaluate is upstream single-stream learned n-gram
row read-ahead. No local speed/acceptance gain is established. Defeated NPU
consumers remain disabled, and neither two-stream MTP nor image generation is
part of this text-serving comparison.

Do not activate this private tree while the user is testing ServiceNow. The
existing controller excludes private directories; later promotion uses the
prepared canonical controller/profile binding and normal singleton lifecycle,
followed by matched measurements and restoration of the ready/open original.
The standing authorization for later measurement restarts remains valid.

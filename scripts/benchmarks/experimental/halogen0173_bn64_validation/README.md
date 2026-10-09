# Isolated BN64 validation fixture

This source archive has no engine detour, NPU path or automatic launcher.
`validator.hip` is a device-only gfx1151 integer validator; `host.c` loads its
module only when explicitly invoked with a module and HIP library path.
`host --oracle-only` performs CPU fixture checks without loading HIP.
Root compiled it with the installed TheRock1151 SDK/code object6/O3 and ran the
bounded owned-buffer helper inside the existing Halogen0.17.3 container.
The two status poison uploads are included in paired timing.

`component-rows.jsonl` contains the exact50 fixture results,256 paired raw timing
rows, and terminal summary. It is not an engine or NPU tok/s benchmark.
See the report for limits and evidence hashes. Do not use these kernels with
unqualified native pointers or attach them to the slower BN64 adapter solely
on the basis of an isolated component win.

`run.py.txt` and `build.py.txt` preserve the executed controls as historical
source, not reusable launchers. The retired root coordinator has a dormant
constructor-recovery gap described in the evidence review. A future harness
requires repair before reuse. No such error occurred in the completed component.

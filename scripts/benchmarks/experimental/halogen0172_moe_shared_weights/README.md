# Standalone shared-weight MoE components

These are the exact executed experimental sources, all serving-off and rejected
for component regressions. They are not drop-in stock GL/FL kernels.

Build the selected `.cpp` with the installed gfx1151 HIP device compiler:
`-x hip --offload-device-only --offload-arch=gfx1151 -mcode-object-version=6
-O3 -fno-fast-math -ffp-contract=off`, then unbundle the resulting device object.
Compile its matching `_host.c` on Linux with
`gcc -std=c11 -O2 -Wall -Wextra -Werror <source> -ldl -lm -o <host>`.
The host takes `native.hsaco candidate.hsaco` and uses the exact retained HIP
runtime path in source. Root executed it with the existing normal WSL/DXG
loader environment in an exclusive idle GPU window with22GiB admission and
continuous18GiB runtime reserves. Do not run a concurrent inference workload.

The native module must be independently obtained from your own Halogen0.17.2
installation and match the module SHA in the evidence. It is not distributed
here. Inputs are generated; these sources include no model payload. Read the
report for finite-fixture, timing and integration limits.

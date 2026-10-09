#!/bin/bash
set -euo pipefail
if [[ "${1:-}" == "--resident-gib" ]]; then
    exec /usr/local/bin/flash_serve "$@"
fi
[[ "${HG0172_HC6_REGISTER_REMAP:-}" == "1" ]]
export LD_PRELOAD="/candidate/libhalogen0172-hc6-register.so:${LD_PRELOAD:?Missing normal preloads}"
exec /usr/local/bin/flash_serve "$@"

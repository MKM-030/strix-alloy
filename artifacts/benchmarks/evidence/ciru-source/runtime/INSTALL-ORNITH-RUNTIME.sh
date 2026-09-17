#!/usr/bin/env bash
set -euo pipefail
task_packages=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
task_root=${1:?usage: INSTALL-ORNITH-RUNTIME.sh NEW_RUNTIME_ROOT}
if [[ -e "$task_root" ]]; then
  printf 'Refusing to overwrite existing runtime: %s\n' "$task_root" >&2
  exit 2
fi
mkdir -p "$task_root"
task_root=$(cd -- "$task_root" && pwd)
# Reuse the qualified wheel installer without modifying its package pins.
export CIRU_RUNTIME_ROOT="$task_root/sources"
export CIRU_VLLM_VENV="$task_root/venv"
bash "$task_packages/INSTALL-RUNTIME.sh"
ln -s sources/vllm-glm53-strix "$task_root/vllm"
ln -s sources/aiter-gfx1151 "$task_root/aiter"
ln -s sources/vllm-glm53-strix/runtime-env.sh "$task_root/runtime-env.sh"
printf 'Ornith runtime prepared. Set ORNITH_RUNTIME_ROOT=%s\n' "$task_root"

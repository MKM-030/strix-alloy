#!/usr/bin/env bash
# Copyright 2026 Ciru. Source only the explicitly selected installed runtime.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime_root=${ORNITH_RUNTIME_ROOT:-}
plugin_site=${ORNITH_PLUGIN_SITE:-$repo_root/.runtime/plugin-site}
cache_directory=${XDG_CACHE_HOME:-$HOME/.cache}/ornith-g256
launch_args=()
while (($#)); do
    case "$1" in
        --runtime-root) runtime_root=${2:?--runtime-root requires a directory}; shift 2 ;;
        --plugin-site) plugin_site=${2:?--plugin-site requires a directory}; shift 2 ;;
        --cache-directory) cache_directory=${2:?--cache-directory requires a directory}; launch_args+=("$1" "$2"); shift 2 ;;
        *) launch_args+=("$1"); shift ;;
    esac
done
if [[ -z "$runtime_root" ]]; then
    echo 'Set --runtime-root DIR (installed Ciru vLLM runtime) or ORNITH_RUNTIME_ROOT.' >&2
    exit 2
fi
test -f "$runtime_root/runtime-env.sh"
test -x "$runtime_root/venv/bin/python"
test -d "$plugin_site/ornith_g256"
export VLLM_SOURCE="$runtime_root/vllm" VLLM_VENV="$runtime_root/venv"
export AITER_SOURCE="$runtime_root/aiter"
export XDG_CACHE_HOME="$cache_directory" AITER_JIT_DIR="$cache_directory/aiter"
# shellcheck source=/dev/null
source "$runtime_root/runtime-env.sh"
unset VLLM_SOURCE VLLM_VENV
export PYTHONPATH="$plugin_site${PYTHONPATH:+:$PYTHONPATH}"
exec "$runtime_root/venv/bin/python" -m ornith_g256.launch "${launch_args[@]}" --cache-directory "$cache_directory"

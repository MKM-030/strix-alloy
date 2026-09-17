#!/usr/bin/env bash
set -Eeuo pipefail

task_package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
task_runtime_root="${CIRU_RUNTIME_ROOT:-/srv/llm/runtime}"
task_venv="${CIRU_VLLM_VENV:-/srv/llm/venvs/vllm-rocm10-gfx1151}"
task_vllm_source="$task_runtime_root/vllm-glm53-strix"
task_aiter_source="$task_runtime_root/aiter-gfx1151"
task_host_library_file="$task_vllm_source/ciru-host-library-path.txt"
task_host_library_path="${CIRU_HOST_LIBRARY_PATH:-}"

if [[ "$task_host_library_path" == *$'\n'* || "$task_host_library_path" == *$'\r'* ]]; then
    printf '%s\n' 'CIRU_HOST_LIBRARY_PATH must be a single colon-separated line.' >&2
    exit 2
fi

for task_command in uv tar install find; do
    command -v "$task_command" >/dev/null || {
        printf 'required command is missing: %s\n' "$task_command" >&2
        exit 2
    }
done

for task_command in gcc g++ git pkg-config xxd; do
    command -v "$task_command" >/dev/null || {
        printf 'AITER JIT build command is missing: %s\n' "$task_command" >&2
        printf '%s\n' 'On NixOS, rerun inside a development shell providing gcc, pkg-config, xxd, libdrm, elfutils, numactl, openssl, and git.' >&2
        exit 2
    }
done

if [[ ! -e /lib64/ld-linux-x86-64.so.2 ]]; then
    printf '%s\n' 'The standard Linux ELF interpreter is unavailable.' >&2
    printf '%s\n' 'On NixOS, enable programs.nix-ld before installing the portable Python/ROCm wheel stack.' >&2
    exit 2
fi

mapfile -t task_vllm_archives < <(find "$task_package_dir" -maxdepth 1 -type f -name 'ciru-halo-agent-vllm-source.tar.gz' -print)
mapfile -t task_aiter_archives < <(find "$task_package_dir" -maxdepth 1 -type f -name 'ciru-halo-agent-aiter-source.tar.gz' -print)
mapfile -t task_vllm_wheels < <(find "$task_package_dir/wheels" -maxdepth 1 -type f -name 'vllm-*.whl' -print)
mapfile -t task_aiter_wheels < <(find "$task_package_dir/wheels" -maxdepth 1 -type f -name 'amd_aiter-*.whl' -print)

test "${#task_vllm_archives[@]}" -eq 1
test "${#task_aiter_archives[@]}" -eq 1
test "${#task_vllm_wheels[@]}" -eq 1
test "${#task_aiter_wheels[@]}" -eq 1
test -f "$task_package_dir/requirements-runtime.lock"
test -f "$task_package_dir/runtime-env.sh"

for task_target in "$task_vllm_source" "$task_aiter_source" "$task_venv"; do
    if [[ -e "$task_target" ]]; then
        printf 'refusing to overwrite existing path: %s\n' "$task_target" >&2
        exit 2
    fi
done

mkdir -p "$task_runtime_root" "$(dirname -- "$task_venv")"
tar -xzf "${task_vllm_archives[0]}" -C "$task_runtime_root"
tar -xzf "${task_aiter_archives[0]}" -C "$task_runtime_root"
install -m 0644 "$task_package_dir/runtime-env.sh" "$task_vllm_source/runtime-env.sh"

printf '%s\n' "$task_host_library_path" > "$task_host_library_file"
chmod 0644 "$task_host_library_file"

uv python install 3.14.3
uv venv --python 3.14.3 "$task_venv"

task_amd_index=https://stable.repo.amd.com/rocm/whl-next/
uv pip install --python "$task_venv/bin/python" \
    --index-url "$task_amd_index" \
    'rocm[libraries,devel,device-gfx1151]==10.0.0' \
    'torch[device-gfx1151]==2.13.0+rocm10.0.0' \
    'torchvision[device-gfx1151]==0.28.0+rocm10.0.0' \
    'torchaudio==2.11.0.2+rocm10.0.0'

# Materialize the SDK compiler/library layout used by the fused ROCm kernels.
"$task_venv/bin/python" -m rocm_sdk init

uv pip install --python "$task_venv/bin/python" \
    --extra-index-url "$task_amd_index" \
    --index-strategy unsafe-best-match \
    -r "$task_package_dir/requirements-runtime.lock"

uv pip install --python "$task_venv/bin/python" --no-deps \
    "${task_aiter_wheels[0]}" "${task_vllm_wheels[0]}"

task_site="$($task_venv/bin/python -c 'import site; print(site.getsitepackages()[0])')"
uv pip install --python "$task_venv/bin/python" \
    "$task_site/_rocm_sdk_core/share/amd_smi"

if [[ -f "$task_package_dir/aiter-jit-gfx1151/module_aiter_core.so" ]]; then
    install -D -m 0755 \
        "$task_package_dir/aiter-jit-gfx1151/module_aiter_core.so" \
        "$task_venv/var/aiter-jit-gfx1151/module_aiter_core.so"
fi

printf '%s\n' 'Runtime engine installed.'
printf 'VLLM_SOURCE=%s\n' "$task_vllm_source"
printf 'AITER_SOURCE=%s\n' "$task_aiter_source"
printf 'VLLM_VENV=%s\n' "$task_venv"
printf 'VLLM_RUNTIME_ENV=%s\n' "$task_vllm_source/runtime-env.sh"
printf 'CIRU_HOST_LIBRARY_PATH_FILE=%s\n' "$task_host_library_file"
printf '%s\n' 'Source runtime-env.sh from the node launcher before starting vLLM.'

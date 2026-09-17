#!/usr/bin/env bash
# Source-only environment for the wheel-installed GLM5.3 Strix runtime.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'source this file; do not execute it directly\n' >&2
    exit 2
fi

: "${VLLM_SOURCE:?set VLLM_SOURCE to /srv/llm/runtime/vllm-glm53-strix}"
: "${VLLM_VENV:?set VLLM_VENV to /srv/llm/venvs/vllm-rocm10-gfx1151}"
: "${AITER_SOURCE:?set AITER_SOURCE to /srv/llm/runtime/aiter-gfx1151}"

python_bin="$VLLM_VENV/bin/python"
[[ -x "$python_bin" ]] || {
    printf 'Python is missing from VLLM_VENV: %s\n' "$python_bin" >&2
    return 2
}

site_packages="$($python_bin - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
rocm_core="${ROCM_CORE_ROOT:-$site_packages/_rocm_sdk_core}"
rocm_devel="${ROCM_DEVEL_ROOT:-$site_packages/_rocm_sdk_devel}"
rocm_libraries="${ROCM_LIBRARIES_ROOT:-$site_packages/_rocm_sdk_libraries}"
torch_lib="$site_packages/torch/lib"

# ROCm 10 wheels may place the compiler and headers in _rocm_sdk_core
# instead of the older _rocm_sdk_devel split.
if [[ -x "$rocm_devel/bin/hipcc" ]]; then
    rocm_tool_root="$rocm_devel"
else
    rocm_tool_root="$rocm_core"
fi
if [[ -x "$rocm_tool_root/lib/llvm/bin/clang" ]]; then
    rocm_llvm_bin="$rocm_tool_root/lib/llvm/bin"
else
    rocm_llvm_bin="$rocm_tool_root/llvm/bin"
fi

for required in \
    "$VLLM_SOURCE/ciru-release/SOURCE_FILES.txt" \
    "$AITER_SOURCE/ciru-release/SOURCE_FILES.txt" \
    "$site_packages/vllm/__init__.py" \
    "$site_packages/aiter/__init__.py" \
    "$rocm_tool_root/bin/hipcc" \
    "$rocm_llvm_bin/clang" \
    "$rocm_llvm_bin/clang++" \
    "$rocm_tool_root/lib" \
    "$rocm_core/lib/llvm/amdgcn/bitcode" \
    "$rocm_core/share/amd_smi" \
    "$torch_lib"; do
    [[ -e "$required" ]] || {
        printf 'required runtime path is missing: %s\n' "$required" >&2
        return 2
    }
done

host_library_path="${CIRU_HOST_LIBRARY_PATH:-}"
if [[ -z "${CIRU_HOST_LIBRARY_PATH+x}" ]]; then
    host_library_file="$VLLM_SOURCE/ciru-host-library-path.txt"
    if [[ -r "$host_library_file" ]]; then
        IFS= read -r host_library_path < "$host_library_file" || host_library_path=""
        export CIRU_HOST_LIBRARY_PATH="$host_library_path"
    fi
fi
rocm_library_path="$rocm_tool_root/lib:$rocm_tool_root/lib/rocm_sysdeps/lib"
rocm_cmake_path="$rocm_tool_root/lib/cmake"
if [[ -d "$rocm_libraries/lib" ]]; then
    rocm_library_path="$rocm_library_path:$rocm_libraries/lib:$rocm_libraries/lib/rocm_sysdeps/lib"
    rocm_cmake_path="$rocm_cmake_path:$rocm_libraries/lib/cmake"
fi
export PATH="$rocm_tool_root/bin:$rocm_llvm_bin:$VLLM_VENV/bin:$PATH"
# Match the working SDK layout: host C++ runtime, expanded ROCm SDK, then Torch.
export LD_LIBRARY_PATH="${host_library_path:+$host_library_path:}$rocm_library_path:$torch_lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [[ -z "${CC:-}" ]]; then
    if command -v cc >/dev/null 2>&1; then
        export CC="$(command -v cc)"
    else
        export CC="$rocm_llvm_bin/clang"
    fi
fi
if [[ -z "${CXX:-}" ]]; then
    if command -v c++ >/dev/null 2>&1; then
        export CXX="$(command -v c++)"
    else
        export CXX="$rocm_llvm_bin/clang++"
    fi
fi
# The extracted source trees are provenance/build inputs. Do not add them to
# PYTHONPATH: doing so would shadow the compiled packages installed by wheel.
export PYTHONPATH="$rocm_core/share/amd_smi${PYTHONPATH:+:$PYTHONPATH}"
export HIP_DEVICE_LIB_PATH="$rocm_core/lib/llvm/amdgcn/bitcode"
export ROCM_PATH="$rocm_tool_root"
export ROCM_HOME="$rocm_tool_root"
export HIP_PATH="$rocm_tool_root"
export CMAKE_PREFIX_PATH="$rocm_cmake_path:$site_packages/torch/share/cmake${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export AITER_JIT_DIR="${AITER_JIT_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/GLM5.3-Flash-CIRU-STRIX-IU4/aiter}"
install -d "$AITER_JIT_DIR" || return 2
aiter_packaged_module="$VLLM_VENV/var/aiter-jit-gfx1151/module_aiter_core.so"
if [[ -f "$aiter_packaged_module" && ! -e "$AITER_JIT_DIR/module_aiter_core.so" ]]; then
    cp -n "$aiter_packaged_module" "$AITER_JIT_DIR/module_aiter_core.so" || return 2
fi

export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"
export ROCR_VISIBLE_DEVICES="${ROCR_VISIBLE_DEVICES:-0}"
export HIP_FORCE_DEV_KERNARG=1
export PYTORCH_ROCM_ARCH=gfx1151
export GPU_ARCHS=gfx1151
export VLLM_TARGET_DEVICE=rocm
export VLLM_ROCM_USE_AITER="${VLLM_ROCM_USE_AITER:-1}"
export VLLM_ROCM_USE_AITER_MOE="${VLLM_ROCM_USE_AITER_MOE:-0}"
export VLLM_ROCM_USE_SKINNY_GEMM="${VLLM_ROCM_USE_SKINNY_GEMM:-0}"
export VLLM_ROCM_MOE_M1_DIRECT_ROUTE="${VLLM_ROCM_MOE_M1_DIRECT_ROUTE:-1}"
export FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE
export VLLM_ENABLE_V1_MULTIPROCESSING="${VLLM_ENABLE_V1_MULTIPROCESSING:-0}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export PYTHONHASHSEED="${PYTHONHASHSEED:-1}"

unset CUDA_VISIBLE_DEVICES
unset host_library_file host_library_path rocm_library_path rocm_cmake_path
unset aiter_packaged_module

#!/usr/bin/env bash
# Probe the WSL/HIP environment for the decode-kernel work. Read-only.
set -x
source /home/revn/ciru-runtime/sources/vllm-glm53-strix/runtime-env.sh 2>&1 | tail -5
export HSA_ENABLE_DXG_DETECTION=1
echo "=== ROCM_PATH=${ROCM_PATH} ==="
echo "=== devices ==="
/home/revn/strix-llama/build-hip/bin/llama-bench --list-devices 2>&1 | tail -8
echo "=== dev nodes ==="
ls -la /dev/dxg 2>/dev/null
ls /dev/kfd 2>/dev/null || echo "no /dev/kfd (expected)"
echo "=== WSL mem ==="
free -g | head -2
echo "=== hipshim / runtime libs in env ==="
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"

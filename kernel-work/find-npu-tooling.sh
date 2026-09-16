#!/usr/bin/env bash
echo "=== NPU-related dirs under C:\\AI ==="
ls /mnt/c/AI/ 2>/dev/null
echo
echo "=== runtimes ==="
ls /mnt/c/AI/runtimes/ 2>/dev/null
echo
echo "=== search for flm / fastflow / npu runtimes ==="
ls -d /mnt/c/AI/*flm* /mnt/c/AI/*FLM* /mnt/c/AI/*npu* /mnt/c/AI/*NPU* 2>/dev/null
find /mnt/c/AI -maxdepth 2 -iname '*flm*' -o -maxdepth 2 -iname '*fastflow*' 2>/dev/null | head
echo
echo "=== NPU driver / libs in System32 ==="
ls /mnt/c/Windows/System32/ 2>/dev/null | grep -iE 'amd.*npu|npu|xilinx|xdna' | head
echo
echo "=== python packages that might drive the NPU ==="
python3 -c "import onnxruntime; print('onnxruntime', onnxruntime.__version__); print([p for p in onnxruntime.get_available_providers()])" 2>&1 | head -5
echo
echo "=== ripgrep-style search for a known NPU runner ==="
ls /mnt/c/AI/runtimes/qwen3-* 2>/dev/null | head

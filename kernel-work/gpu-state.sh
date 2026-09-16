#!/usr/bin/env bash
# gpu-state.sh — is the iGPU throttled / clocked low? amd-smi over DXG may expose telemetry.
echo "=== amd-smi (WSL, DXG) ==="
which amd-smi 2>/dev/null && amd-smi metric 2>&1 | head -30 || echo "amd-smi not on PATH"
echo
echo "=== try the ciru venv's amd-smi ==="
/home/revn/ciru-runtime/venv/bin/python -c "import amdsmi; print('amdsmi module OK')" 2>&1 | head -2
echo
echo "=== sysfs / hwmon clocks (may be absent on WSL) ==="
ls /sys/class/drm/ 2>/dev/null | head -5
cat /sys/class/drm/card0/device/pp_dpm_sclk 2>/dev/null | head -5 || echo "no pp_dpm_sclk"
echo
echo "=== memory bandwidth probe: how fast can we read RAM? ==="
python3 - <<'PY' 2>/dev/null || echo "(skipping dd)"
PY
dd if=/dev/zero of=/dev/null bs=1M count=4000 2>&1 | tail -1

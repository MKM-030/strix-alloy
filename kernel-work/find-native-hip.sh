#!/usr/bin/env bash
# Find every native Windows HIP runtime/binary on the box, plus boot time and SDK integrity.
echo "=== boot / uptime ==="
cmd.exe /c "powershell -NoProfile -Command \"(Get-CimInstance Win32_OperatingSystem).LastBootUpTime\"" 2>/dev/null | tr -d '\r'

echo
echo "=== runtimes that look native (non-vulkan, non-wsl) ==="
for d in /mnt/c/AI/runtimes/*/; do
  n=$(basename "$d")
  exe=$(ls "$d"llama-server.exe "$d"bin/llama-server.exe 2>/dev/null | head -1)
  [ -n "$exe" ] && echo "  $n -> $exe"
done

echo
echo "=== which of those link ROCm/HIP vs Vulkan? ==="
for exe in $(find /mnt/c/AI/runtimes -maxdepth 2 -name 'llama-server.exe' 2>/dev/null); do
  dlls=$(ls "$(dirname "$exe")"/*.dll 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')
  echo "  $(dirname "$exe")"
  echo "     dlls: $dlls"
done

echo
echo "=== TheRock SDK bin: is amdhip64.dll actually present? ==="
ls -la /mnt/c/AI/sdk/therock1151/bin/ 2>/dev/null | head -40

echo
echo "=== search for amdhip64.dll anywhere on C: (limited depth) ==="
find /mnt/c/AI -maxdepth 4 -iname 'amdhip64.dll' 2>/dev/null | head
find /mnt/c/Windows/System32 -maxdepth 1 -iname 'amdhip64.dll' 2>/dev/null | head

echo
echo "=== other SDKs present? ==="
ls -d /mnt/c/AI/sdk/* 2>/dev/null

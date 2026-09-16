#!/usr/bin/env bash
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama
echo "=== does the WINDOWS source have the 2nd patch (cap_branch)? ==="
grep -c 'cap_branch' "$W/ggml/src/ggml-cuda/ggml-cuda.cu" 2>/dev/null
echo "=== and the WSL source? ==="
grep -c 'cap_branch' "$S/ggml/src/ggml-cuda/ggml-cuda.cu" 2>/dev/null
echo
echo "=== timestamps: source vs built dll ==="
stat -c '%y  %n' "$W/ggml/src/ggml-cuda/ggml-cuda.cu" 2>/dev/null
stat -c '%y  %n' "$W/build-therock/bin/ggml-hip.dll" 2>/dev/null
echo
echo "=== is the object file newer than the source? ==="
find "$W/build-therock" -name 'ggml-cuda.cu.obj' -exec stat -c '%y  %n' {} \; 2>/dev/null
echo
echo "=== does the built DLL contain the diagnostic string? ==="
for dll in "$W/build-therock/bin/ggml-hip.dll"; do
  echo "  $dll"
  for s in 'OP_TIMING_IG DIAG' 'cap_branch' 'cap_nodes'; do
    if grep -q "$s" "$dll" 2>/dev/null; then echo "      HAS: $s"; else echo "      no : $s"; fi
  done
  for s in 'record_calls'; do
    if grep -q "$s" "$dll" 2>/dev/null; then echo "      HAS: $s"; else echo "      no : $s"; fi
  done
done

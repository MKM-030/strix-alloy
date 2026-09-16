# test-gfx1151.ps1 — verify ROCm 7.2's clang can compile HIP for gfx1151 on Windows.
$ErrorActionPreference = 'Continue'
$rocm = 'C:\Program Files\AMD\ROCm\7.2'
Write-Output "clang: $(& "$rocm\bin\clang.exe" --version 2>&1 | Select-Object -First 1)"
Write-Output "hipcc: $(Test-Path "$rocm\bin\hipcc.exe")"
Write-Output "--- amdgcn bitcode dir ---"
Get-ChildItem "$rocm\amdgcn\bitcode" -ErrorAction SilentlyContinue | Select-Object -First 5 -ExpandProperty Name
Write-Output "--- gfx1151 device libs present? ---"
$libs = Get-ChildItem "$rocm" -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'gfx1151' }
Write-Output "count=$($libs.Count)"
$libs | Select-Object -First 5 -ExpandProperty FullName

Write-Output "--- compile test ---"
$tmp = Join-Path $env:TEMP 'gfxtest'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$src = Join-Path $tmp 't.hip'
Set-Content -Path $src -Value @'
#include <hip/hip_runtime.h>
__global__ void k(float*o){ o[0]=1.0f; }
int main(){ float *d; hipMalloc(&d,4); k<<<1,1>>>(d); hipDeviceSynchronize(); return 0; }
'@
$env:HIP_PATH = $rocm
$env:ROCM_PATH = $rocm
& "$rocm\bin\hipcc.exe" --offload-arch=gfx1151 -o (Join-Path $tmp 'gfxtest.exe') $src 2>&1 | Select-Object -First 8
Write-Output "compile exit=$LASTEXITCODE"
Write-Output "exe exists: $(Test-Path (Join-Path $tmp 'gfxtest.exe'))"

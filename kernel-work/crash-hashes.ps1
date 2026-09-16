# crash-hashes.ps1 - emit every hash a reader needs to reproduce a headline number.
$bin = 'C:\AI\build\strix-llama-win\build-therock\bin'

Write-Output '### BINARIES ###'
foreach ($f in @('llama-server.exe', 'ggml-hip.dll', 'ggml.dll', 'llama-server-impl.dll', 'llama-common.dll')) {
    $p = Join-Path $bin $f
    if (Test-Path $p) {
        $h = (Get-FileHash $p -Algorithm SHA256).Hash
        $sz = (Get-Item $p).Length
        Write-Output ("  {0,-24} {1,12} {2}" -f $f, $sz, $h)
    }
}

Write-Output '### MODEL SHARDS ###'
Get-ChildItem 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-*.gguf' |
    Sort-Object Name | ForEach-Object {
        $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        Write-Output ("  {0,-54} {1}" -f $_.Name, $h)
    }

Write-Output '### DRAFT HEAD ###'
Get-ChildItem 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf' | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    Write-Output ("  {0,-54} {1}" -f $_.Name, $h)
}

Write-Output '### PATCH SERIES HASHES ###'
Get-ChildItem 'C:\Projects\strix-alloy-clean\engine-patches\*.patch' | Sort-Object Name | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    Write-Output ("  {0,-64} {1}" -f $_.Name, $h.Substring(0, 32))
}

Write-Output '### SDK / COMPILER ###'
$clang = 'C:\AI\sdk\therock1151\lib\llvm\bin\clang.exe'
if (Test-Path $clang) {
    $v = (& $clang --version 2>&1 | Select-Object -First 1)
    Write-Output ("  clang: $v")
}
$hip = 'C:\AI\sdk\therock1151\bin\amdhip64_7.dll'
if (Test-Path $hip) {
    Write-Output ("  amdhip64_7.dll  {0,12} {1}" -f (Get-Item $hip).Length, (Get-FileHash $hip -Algorithm SHA256).Hash)
}

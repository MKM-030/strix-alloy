param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$GitExe,
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$BuildDir,
    [Parameter(Mandatory = $true)][string]$SdkDir,
    [Parameter(Mandatory = $true)][string]$VcpkgDir,
    [Parameter(Mandatory = $true)][string]$VcVars64,
    [Parameter(Mandatory = $true)][string]$CMakeExe,
    [Parameter(Mandatory = $true)][string]$NinjaExe,
    [string]$Jobs = '2'
)

$ErrorActionPreference = 'Stop'

try {
    if ($Jobs -cnotmatch '^[12]$') {
        throw 'Jobs must be exactly 1 or 2.'
    }
    $python = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).ProviderPath
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'PythonExe must name an existing file.'
    }
    $scripts = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\scripts') -ErrorAction Stop).ProviderPath
    $entry = 'import sys; sys.path.insert(0, sys.argv[1]); from gufo_control.build_setup import main; raise SystemExit(main(sys.argv[2:]))'
    $childArgs = @('-c', $entry, $scripts,
        '--python-exe', $python, '--git-exe', $GitExe,
        '--source-dir', $SourceDir, '--build-dir', $BuildDir,
        '--sdk-dir', $SdkDir, '--vcpkg-dir', $VcpkgDir,
        '--vcvars64', $VcVars64, '--cmake-exe', $CMakeExe,
        '--ninja-exe', $NinjaExe, '--jobs', $Jobs)
    & $python @childArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine("refused: $($_.Exception.Message)")
    exit 2
}

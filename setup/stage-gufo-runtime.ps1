param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$RuntimeDir,
    [ValidateSet('baseline', 'service-ar4k-v1', 'service-ar4k-header-v1')][string]$RuntimeVariant = 'baseline',
    [switch]$Verify,
    [string]$BuildDir,
    [string]$SdkDir,
    [string]$VcpkgDir
)

$ErrorActionPreference = 'Stop'

try {
    $python = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).ProviderPath
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'PythonExe must name an existing file.'
    }
    $scripts = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\scripts') -ErrorAction Stop).ProviderPath
    $entry = 'import sys; sys.path.insert(0, sys.argv[1]); from gufo_control.runtime_package import main; raise SystemExit(main(sys.argv[2:]))'
    $childArgs = @('-c', $entry, $scripts)
    if ($Verify) {
        $childArgs += @('verify', '--runtime-dir', $RuntimeDir)
    } else {
        if (-not $BuildDir -or -not $SdkDir -or -not $VcpkgDir) {
            throw 'Stage requires BuildDir, SdkDir, and VcpkgDir explicitly.'
        }
        $childArgs += @('stage', '--build-dir', $BuildDir, '--sdk-dir', $SdkDir,
                        '--vcpkg-dir', $VcpkgDir, '--runtime-dir', $RuntimeDir)
    }
    $childArgs += @('--runtime-variant', $RuntimeVariant)
    & $python @childArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine("refused: $($_.Exception.Message)")
    exit 2
}

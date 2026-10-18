param(
    [string]$Command,
    [string]$PythonExe
)

$ErrorActionPreference = 'Stop'

function Refuse([string]$Reason, [string]$Evidence) {
    [Console]::Error.WriteLine("refused: $Reason Evidence: $Evidence")
    exit 2
}

if ($args.Count -ne 0) {
    Refuse "Unsupported arguments: $($args -join ' ')" $MyInvocation.MyCommand.Path
}
if ($Command -cnotin @('start', 'print-only', 'status', 'stop')) {
    Refuse "Unsupported command '$Command'; use start, print-only, status, or stop." $MyInvocation.MyCommand.Path
}

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$scripts = Join-Path $root 'scripts'
$controller = Join-Path $scripts 'gufo_control\service.py'
$profile = Join-Path $root 'config\gufo-service-profile.json'

if (-not $PythonExe -or -not [IO.Path]::IsPathRooted($PythonExe) -or
        -not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    $pythonEvidence = if ($PythonExe) { $PythonExe } else { '-PythonExe' }
    Refuse 'PythonExe must name an existing absolute Python executable file.' $pythonEvidence
}
if (-not (Test-Path -LiteralPath $controller -PathType Leaf)) {
    Refuse 'GUFO service controller package is missing.' $controller
}
if (-not (Test-Path -LiteralPath $profile -PathType Leaf)) {
    Refuse 'Installed GUFO profile is missing.' $profile
}

try {
    $python = (Resolve-Path -LiteralPath $PythonExe).ProviderPath
    $scripts = (Resolve-Path -LiteralPath $scripts).ProviderPath
    $profile = (Resolve-Path -LiteralPath $profile).ProviderPath
    $entry = 'import sys; sys.path.insert(0, sys.argv[1]); from gufo_control.service import main; raise SystemExit(main(sys.argv[2:]))'
    & $python -B -c $entry $scripts $Command '--profile' $profile
    $code = $LASTEXITCODE
    if ($null -eq $code) { Refuse 'Python did not return an exit code.' $python }
    if ($code -eq 2) {
        $evidence = "profile=$profile"
        try {
            $record = Get-Content -LiteralPath $profile -Raw | ConvertFrom-Json
            if ($record.evidence) {
                $evidence = "qualification=$($record.evidence.acceptance); runs=$($record.evidence.runs)"
            }
        } catch {
            # The CLI owns profile validation; its result and exit code remain authoritative.
        }
        [Console]::Error.WriteLine("GUFO service returned exit 2 (refusal or indeterminate handoff). Evidence: $evidence")
    }
    exit $code
} catch {
    Refuse $_.Exception.Message $controller
}

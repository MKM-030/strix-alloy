#requires -Version 7.0
<#
Read-only backend discovery. This is not a model manager or a start/stop switch.
Native PrintOnly returns an argument vector; it does not invoke the launcher.
No installation, inference, endpoint rewrite or silent fallback is performed.
#>
[CmdletBinding(PositionalBinding=$false)]
param(
    [Parameter(Mandatory)][ValidateSet('Native','Projfix','Halogen','GUFO')]
    [string]$Backend,
    [Parameter(Mandatory)][ValidateSet('Describe','PrintOnly')]
    [string]$Action,
    [string]$ModelDir,
    [string]$RuntimeDir,
    [string]$DraftPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Refuse([string]$Message) {
    [Console]::Error.WriteLine("refused: $Message")
    exit 2
}
function Absolute-Existing([string]$Value, [string]$Kind, [string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Value) -or
        -not [IO.Path]::IsPathFullyQualified($Value) -or
        -not (Test-Path -LiteralPath $Value -PathType $Kind)) {
        Refuse "$Name must name an existing absolute $Kind path."
    }
    return (Resolve-Path -LiteralPath $Value).ProviderPath
}
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$name = if ($Backend -eq 'Projfix') { 'native' } else { $Backend.ToLowerInvariant() }
if ($Action -eq 'Describe') {
    if ($ModelDir -or $RuntimeDir -or $DraftPath) {
        Refuse 'Describe accepts no model/runtime/draft arguments and probes no installation.'
    }
    $records = @{
        native = @{
            status='published_native'; model_format='PROJFIX GGUF; optional matching MTP GGUF'
            launcher='app/launch-flash-next.ps1'; api='http://127.0.0.1:8826/v1'
            qualification='Published native Windows 96 GiB carve profile; do not change BIOS automatically.'
            start_command='.\app\launch-flash-next.ps1 -ModelDir <absolute-directory> -RuntimeDir <absolute-runtime>'
            print_only_supported=$true
        }
        halogen = @{
            status='experimental_guarded_service'; model_format='HGN checkpoint + overlay + tokenizer on WSL Ext4'
            version='0.15.1'; launcher='backends/halogen-wsl2-0.15.1/Start.ps1'; api='http://127.0.0.1:8731/v1'
            qualification='Pinned 0.15.1; configurable context, default 129024; continuous serving, Bearer auth, live logs.'
            start_command='.\backends\halogen-wsl2-0.15.1\Start.ps1 -ContextSize 129024'
            print_only_supported=$false
        }
        gufo = @{
            status='experimental_local_qualification_required'; model_format='GUFO-compatible GGUF + shared MTP sidecar; not HGN'
            launcher='server/Start.ps1'; api='http://127.0.0.1:8840/v1'; start_command='.\server\Start.ps1 -Backend GUFO -ContextSize 262144'
            qualification='Pinned TheRock 10.2.0a20260930 with the numerical compatibility patch; Build, Qualify and Register a local profile before serving. See backends/gufo-windows.'
            print_only_supported=$false
        }
    }
    $record = $records[$name]
    $record.backend = $name
    $record.schema = 'strix-backend-description-v1'
    $record.selector_starts_models = $false
    $record.single_shared_endpoint = $false
    $record | ConvertTo-Json -Depth 4
    exit 0
}
if ($name -ne 'native') {
    Refuse "$Backend has no qualified PrintOnly command here. Use Describe; nothing was started."
}
$model = Absolute-Existing $ModelDir 'Container' 'ModelDir'
$runtime = Absolute-Existing $RuntimeDir 'Container' 'RuntimeDir'
$launcher = Join-Path $root 'app/launch-flash-next.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    Refuse 'The original native launcher is missing from this checkout.'
}
$arguments = @('-PrintOnly','-ModelDir',$model,'-RuntimeDir',$runtime)
if ($DraftPath) {
    $draft = Absolute-Existing $DraftPath 'Leaf' 'DraftPath'
    $arguments += @('-DraftPath',$draft)
}
# Return an argument vector, never evaluate or execute a constructed command.
@{ schema='strix-backend-plan-v1'; backend='native'; executed=$false;
   launcher=$launcher; arguments=$arguments;
   note='Run the original launcher with these arguments to perform its own checks.'
} | ConvertTo-Json -Depth 4

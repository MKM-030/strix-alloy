# Offline policy checks only: extract functions, never execute the model wrapper.
$ErrorActionPreference = 'Stop'
$wrapper = Join-Path $PSScriptRoot '../../scripts/gufo_control/reddit_halogen_run.ps1'
. (Join-Path $PSScriptRoot '../../scripts/gufo_control/reddit_halogen_controller.ps1')
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($wrapper,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Wrapper parse failed' }
foreach($name in @('Assert-Review','Get-WindowsLaunchReserve','Check-Floors','Assert-HostHeartbeat','New-RedditArguments')) {
    $definition=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
    . ([scriptblock]::Create($definition.Extent.Text))
}
function Expect-Rejection([scriptblock]$Run) {
    $rejected=$false
    try { & $Run | Out-Null } catch { $rejected=$true }
    if (-not $rejected) { throw 'Expected policy rejection' }
}
$reviewPath=Join-Path ([IO.Path]::GetTempPath()) ('halogen-policy-'+[guid]::NewGuid().ToString('N')+'.json')
$heartbeatPath=$reviewPath+'.jsonl'
$plan=[pscustomobject]@{binding_sha256='offline-test-binding'}
$record=@{decision='approved'; binding_sha256=$plan.binding_sha256;
    admission_min_bytes=55029268480L; planned_commit_growth_bytes=86GB;
    allocation_reason='Preserved empirical estimate; explicit user waiver only.';
    runtime_physical_floor_bytes=12GB;
    runtime_physical_floor_authorization='Ja von 24 auf 12';
    physical_start_waiver_authorization='Ignorier die Grenze mach weiter'}
function Save-Record { [IO.File]::WriteAllText($reviewPath,($record|ConvertTo-Json)) }
try {
    Save-Record
    $UserWaivePhysicalStartEstimate=$false
    $null=Assert-Review $plan
    if ($script:admissionMinBytes -ne 55029268480L) { throw 'Default admission changed' }
    $UserWaivePhysicalStartEstimate=$true
    $null=Assert-Review $plan
    if ($script:admissionMinBytes -ne 24GB) { throw 'Explicit waiver did not use retained 24 GiB floor' }
    if ($script:plannedCommitGrowthBytes -ne 86GB) { throw 'Commit allowance changed' }
    $record.physical_start_waiver_authorization=''; Save-Record
    Expect-Rejection { Assert-Review $plan }
    $record.physical_start_waiver_authorization='Ignorier die Grenze mach weiter'
    $record.admission_min_bytes=24GB; Save-Record
    Expect-Rejection { Assert-Review $plan }
    $record.admission_min_bytes=55029268480L
    $record.planned_commit_growth_bytes=85GB; Save-Record
    Expect-Rejection { Assert-Review $plan }
    $record.planned_commit_growth_bytes=86GB
    $record.binding_sha256='wrong'; Save-Record
    Expect-Rejection { Assert-Review $plan }
    $record.binding_sha256=$plan.binding_sha256; Save-Record
    $null=Assert-Review $plan
    # Only the OS counter input is synthetic; execute the real floor/admission checks.
    function Get-MemoryFrame { return $script:testFrame }
    $script:testFrame=@{availableBytes=48GB; commitHeadroomBytes=200GB}
    if ((Get-WindowsLaunchReserve) -ne 48GB) { throw 'Authorized launch rejected' }
    $script:testFrame.availableBytes=18GB
    $null=Check-Floors ''
    $script:testFrame.availableBytes=12GB-1
    Expect-Rejection { Check-Floors '' }
    $record.runtime_physical_floor_authorization=''; Save-Record
    Expect-Rejection { Assert-Review $plan }
    $record.runtime_physical_floor_authorization='Ja von 24 auf 12'; Save-Record
    $script:testFrame.availableBytes=24GB-1
    Expect-Rejection { Get-WindowsLaunchReserve }
    $script:testFrame.availableBytes=48GB
    $script:testFrame.commitHeadroomBytes=98GB-1
    Expect-Rejection { Get-WindowsLaunchReserve }
    $script:testFrame.commitHeadroomBytes=12GB-1
    Expect-Rejection { Check-Floors '' }
    if ('UserWaivePhysicalStartEstimate' -notin $ast.ParamBlock.Parameters.Name.VariablePath.UserPath) {
        throw 'Explicit command switch missing'
    }
    [IO.File]::WriteAllText($heartbeatPath,(@{event='sample';utc=[DateTimeOffset]::UtcNow.ToString('o');
        available_bytes=18GB;commit_headroom_bytes=200GB}|ConvertTo-Json -Compress))
    $ownProcess=[Diagnostics.Process]::GetCurrentProcess()
    try { Assert-HostHeartbeat $heartbeatPath $ownProcess } finally { $ownProcess.Dispose() }
    # Compare the real generated container environment with the working deployment,
    # not merely the old historical base. This validates pinned files offline only.
    $sealedBuild=Assert-PreflightBuild
    $reference=@(Get-Content -LiteralPath (Join-Path $root 'results/halogen-performance-20260924/publication-repeat3-inspect.json') -Raw|ConvertFrom-Json)[0]
    $generated=New-RedditArguments $reference @{adapters=$sealedBuild.adapters} 'offline-no-container'
    $generatedEnv=@{}
    for($i=0;$i -lt $generated.Count-1;$i++) {
        if($generated[$i] -eq '--env') {
            $pair=$generated[$i+1] -split '=',2
            if($generatedEnv.ContainsKey($pair[0])) { throw 'Duplicate generated environment' }
            $generatedEnv[$pair[0]]=$pair[1]
        }
    }
    $profile=Get-Content -LiteralPath 'C:/Projects/strix-alloy-wsl2/profiles/environment.json' -Raw|ConvertFrom-Json
    $expectedEnv=@{}
    foreach($entry in $profile.environment) { $pair=$entry -split '=',2; $expectedEnv[$pair[0]]=$pair[1] }
    foreach($pair in @{HALOGEN_CTX='133888';HALOGEN_KV_POOL_POSITIONS='133888';HALOGEN_PROMPT_CACHE='2';HALOGEN_CACHE_BRANCHES='2';HALOGEN_CACHE_INPLACE='1';HALOGEN_CACHE_SNAP3='0';HALOGEN_CACHE_FULL='0';HALOGEN_CACHE_ENTRIES='3'}.GetEnumerator()) { $expectedEnv[$pair.Key]=$pair.Value }
    foreach($key in $expectedEnv.Keys) {
        if($generatedEnv[$key] -cne $expectedEnv[$key]) { throw "Working environment mismatch: $key" }
    }
    if($generatedEnv.Count -ne $expectedEnv.Count) { throw 'Unexpected environment fields' }
    if(($ast.Extent.Text -split '\$admission = Assert-Admission -Mode ',2)[1] -notlike "'PreflightPinned32k'*") {
        throw 'Working sealed admission path not selected'
    }
    'PASS: default admission, explicit authorization, binding, commit planning and runtime floors'
} finally {
    if (Test-Path -LiteralPath $reviewPath) { Remove-Item -LiteralPath $reviewPath }
    if (Test-Path -LiteralPath $heartbeatPath) { Remove-Item -LiteralPath $heartbeatPath }
}

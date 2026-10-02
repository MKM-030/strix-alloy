# Portable boundaries used by the frozen controller copy. No shell interpolation.
function ConvertTo-NativeArgument([string]$Value) {
    if($Value.Length -gt 0 -and $Value -notmatch '[\s"]'){return $Value}
    '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Start-PortableProcess {
    param([string]$FilePath, [string]$WindowStyle, [switch]$PassThru,
          [string[]]$ArgumentList, [string]$RedirectStandardOutput, [string]$RedirectStandardError)
    foreach($path in @($RedirectStandardOutput,$RedirectStandardError)) {
        if($path -and (Test-Path -LiteralPath $path)){throw "Refusing to overwrite helper output: $path"}
    }
    $quoted=@($ArgumentList | ForEach-Object { ConvertTo-NativeArgument $_ })
    Start-Process -FilePath $FilePath -WindowStyle Hidden -PassThru -ArgumentList $quoted `
        -RedirectStandardOutput $RedirectStandardOutput -RedirectStandardError $RedirectStandardError
}

function Initialize-PublicMachine {
    $path=Join-Path $root '.local/machine.json'
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)){throw 'Run Install.ps1 -Install first.'}
    $script:machine=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -ErrorAction Stop
    if($machine.schema -cne 'strix-alloy-machine-v1' -or $machine.profile -cne 'flash0138-copy48-v1') {
        throw 'Unrecognized machine configuration'
    }
    $script:wslArgs=@('-d',$machine.distro,'-u',$machine.user,'--exec')
    $script:guardArgs=@('--distro',$machine.distro,'--user',$machine.user,'--models',$machine.models,
                       '--workspace',$machine.workspace,'--dxg',$machine.dxg)
}

function Get-PublicBinds {
    return @('/usr/lib/wsl/lib/libdxcore.so:/usr/lib/libdxcore.so:ro',
             ($machine.dxg + ':/usr/lib/librocdxg.so:ro'),
             ($machine.models + ':/models:ro'),($machine.workspace + ':/workspace:ro'))
}

function Get-PublicReference {
    Assert-Hash (Join-Path $root 'profiles/environment.json') 'a929f73ac1aa2649fe0735229e8d6d8b43a2f59c768e2d0ff3a393bb7437e087' | Out-Null
    $template=Get-Content -LiteralPath (Join-Path $root 'profiles/environment.json') -Raw | ConvertFrom-Json
    if($template.image -cne $image){throw 'Public template image identity changed'}
    return [pscustomobject]@{Config=[pscustomobject]@{Image=$image;Env=@($template.environment)};
                            HostConfig=[pscustomobject]@{Binds=@(Get-PublicBinds)}}
}

function Assert-PublicAdmission {
    & $python -B (Join-Path $root 'scripts/package.py') validate
    if($LASTEXITCODE -ne 0){throw 'Portable machine, dependency, source or model admission failed'}
    $physical=[int64]((Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum)
    $visible=[int64](Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize * 1024
    if($physical -ne 128GB -or $visible -ne 68340748288){throw 'Only the qualified 128 GiB / VGM64 Windows memory profile is admitted'}
    $available=Get-WindowsLaunchReserve
    $live=Invoke-WslBounded -Arguments @('docker','ps','--format','{{.ID}} {{.Names}}')
    if($live){throw 'Require no running containers'}
    if(@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^llama-server(\.exe)?$'}).Count){throw 'Native llama-server must not overlap'}
    $guest=Invoke-WslBounded -Arguments @('cat','/proc/meminfo')
    if($guest -notmatch '(?m)^MemTotal:\s+(\d+) kB$' -or [int64]$Matches[1] -lt 54GB/1KB -or [int64]$Matches[1] -gt 56GB/1KB){
        throw 'WSL guest memory disagrees with admitted 56GB configuration'
    }
    if($guest -notmatch '(?m)^MemAvailable:\s+(\d+) kB$' -or [int64]$Matches[1] -lt 12GB/1KB){throw 'Require at least 12 GiB guest available'}
    $build=Assert-PreflightBuild
    $available=Get-WindowsLaunchReserve
    return @{available=$available;visible=$visible;physical=$physical;adapters=$build.adapters;
             engineSha256=$build.engineSha256;preflightBuildSha256='4ba62f3db0359b6bf4a3f3a0727ab4bb3992cd64f7326469b0794b0a213d9edd'}
}

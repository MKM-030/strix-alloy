# CPU-only: no WSL, Docker, model, GPU or settings operations.
#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../tools/qualification/qualify-hybrid48-model.ps1')
function Assert($Condition,[string]$Message){if(-not $Condition){throw $Message}}
Assert ($null -ne (Get-Command Get-PublicReference -ErrorAction SilentlyContinue)) 'Public environment admission is missing'
$machine=[pscustomobject]@{distro='Other-Distro';user='alice';models='/home/alice/model files';workspace='/mnt/c/package files';dxg='/opt/dxg.so'}
$reference=Get-PublicReference
$admission=@{adapters=@((Get-Content (Join-Path $root 'profiles/build.json') -Raw | ConvertFrom-Json).adapters)}
$run=New-RunArguments $reference $admission 'halogen-flash-hybrid-test' -Mode PreflightServe32k
Assert ($run -contains '/home/alice/model files:/models:ro') 'Model bind must preserve spaces and read-only mode'
Assert ($run -contains '/mnt/c/package files:/workspace:ro') 'Workspace must be read-only'
Assert ($run -contains '/opt/dxg.so:/usr/lib/librocdxg.so:ro') 'DXG must be read-only'
Assert ($run -contains 'HALOGEN_CTX=32768') 'Serve32k context changed'
Assert ($run -contains 'HALOGEN_KV_SLOTS=1') 'Serve32k slot count changed'
Assert ($run -contains '127.0.0.1:8731:8731') 'Loopback changed'
Assert (($run | Where-Object {$_ -eq '47244640256'}).Count -eq 2) 'Cgroup memory/swap bounds changed'
$spec=Get-QualificationProbeSpec -Mode PreflightServe32k
Assert ($spec.Script -ceq 'serve32k.py') 'Serving must not launch benchmark traffic'
$argsServe=Get-QualificationProbeArguments $spec PreflightServe32k 350 'C:/run path'
Assert ($argsServe -contains '300') 'Serve duration forwarding missing'
$before=$reference.Config.Env
$reference.Config.Env+=@($reference.Config.Env[0])
$rejected=$false
try { New-RunArguments $reference $admission 'x' -Mode PreflightServe32k } catch {$rejected=$true}
Assert $rejected 'Duplicate environment must refuse'
$reference.Config.Env=$before
$escaped=ConvertTo-NativeArgument 'C:\path with spaces\'
Assert ($escaped -ceq '"C:\path with spaces\\"') 'Native quoting must preserve trailing backslash'
foreach($switch in @('-d','-u','--exec')) {
    Assert ((ConvertTo-NativeArgument $switch) -ceq $switch) "WSL option $switch must remain an unquoted native argument"
}
foreach($plain in @('Ubuntu-24.04','alice','/usr/bin/printf')) {
    Assert ((ConvertTo-NativeArgument $plain) -ceq $plain) "Plain argument $plain must not be gratuitously quoted"
}
class OwnedProcessFixture {
    [bool]$HasExited=$false
    [bool]$Tree=$false
    [int]$ExitCode=0
    [void] Refresh(){}
    [void] Kill([bool]$tree){$this.Tree=$tree;$this.HasExited=$true}
    [void] Kill(){$this.HasExited=$true}
    [bool] WaitForExit([int]$millis){return $this.HasExited}
}
$owned=[OwnedProcessFixture]::new()
Stop-HelperChecked $owned -Tree
Assert ($owned.Tree -and $owned.HasExited) 'Owned process tree cleanup must be checked'
$remaining=Get-RemainingInferenceSeconds -InferenceElapsed 10 -OverallElapsed 815 -Mode PreflightServe32k
Assert ($remaining -eq 5) 'Overall 820-second bound changed'
Write-Output 'PASS portable controller (bindings, profiles, quoting, duplicate environment, tree cleanup, deadline)'
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('strix-alloy-quoted-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
$out=Join-Path $temporary 'out with spaces.json'
$err=Join-Path $temporary 'err with spaces.log'
$p=$null
try {
    $values=@('','C:\path with spaces\','embedded"quote','dollar$and;semicolon','Unicode-ä')
    $p=Start-PortableProcess -FilePath $python -ArgumentList (@('-B','-c','import json,sys; print(json.dumps(sys.argv[1:]))')+$values) -RedirectStandardOutput $out -RedirectStandardError $err
    if(-not $p.WaitForExit(5000)){throw 'Argument round-trip helper timed out'}
    if($p.ExitCode -ne 0){throw (Get-Content $err -Raw)}
    $actual=@(Get-Content $out -Raw | ConvertFrom-Json)
    Assert (($actual -join '|') -ceq ($values -join '|')) 'Native arguments did not survive quoting exactly'
} finally {
    if($p){Stop-HelperChecked $p -Tree;$p.Dispose()}
    foreach($path in @($out,$err)){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path}}
    Remove-Item -LiteralPath $temporary
}
Write-Output 'PASS real native argument round-trip (spaces, quotes, trailing slash, shell metacharacters, Unicode)'

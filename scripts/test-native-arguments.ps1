# Run in Windows PowerShell 5.1 or PowerShell 7. No model/runtime is started.
# -ReproduceOldBug deliberately fails using Start-Process's old array handling.
[CmdletBinding()]
param([switch]$ReproduceOldBug)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    throw "The Windows .NET Framework compiler is required for this argument test: $compiler"
}
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('strix-alloy-argv-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null

try {
    $sourceFile = Join-Path $scratch 'ArgumentEcho.cs'
    $echoExe = Join-Path $scratch 'ArgumentEcho.exe'
    $stdout = Join-Path $scratch 'stdout.txt'
    $stderr = Join-Path $scratch 'stderr.txt'
    @'
using System;
using System.Text;
public static class ArgumentEcho {
    public static int Main(string[] args) {
        foreach (string arg in args) {
            Console.WriteLine(Convert.ToBase64String(Encoding.UTF8.GetBytes(arg)));
        }
        return 0;
    }
}
'@ | Set-Content -LiteralPath $sourceFile -Encoding UTF8
    & $compiler /nologo /target:exe "/out:$echoExe" $sourceFile
    if ($LASTEXITCODE -ne 0) { throw "Argument helper compilation failed: $LASTEXITCODE" }

    $expected = @(
        '--chat-template-file',
        'C:\Program Files\strix-alloy\app\flash-next-clients.jinja',
        '-m', 'C:\AI Models\Qwen Flash\model.gguf',
        'plain', '',
        'contains "quoted" text',
        'C:\folder with spaces\',
        'C:\folder\',
        'backslash-before-quote\"value',
        'two-backslashes-before-quote\\"value',
        'two trailing slashes\\',
        "tab`tseparated"
    )

    if ($ReproduceOldBug) {
        # The old array also rejects empty elements before starting the child;
        # use only real launcher flags here to demonstrate the path split itself.
        $expected = $expected[0..3]
        $nativeArguments = $expected
    } else {
        # Load only the encoder's AST; dot-sourcing the launcher would start a model.
        $launcher = Join-Path (Split-Path $PSScriptRoot -Parent) 'app\launch-flash-next.ps1'
        $tokens = $null
        $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$parseErrors)
        if ($parseErrors.Count) { throw "Launcher parse failed: $($parseErrors[0].Message)" }
        $encoder = $ast.Find({ param($node)
            $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq 'ConvertTo-WindowsArgument'
        }, $true)
        if ($null -eq $encoder) { throw 'Launcher has no ConvertTo-WindowsArgument function.' }
        . ([scriptblock]::Create($encoder.Extent.Text))
        $nativeArguments = ($expected | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' '
    }

    $child = Start-Process -FilePath $echoExe -ArgumentList $nativeArguments -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -Wait -PassThru
    if ($child.ExitCode -ne 0) { throw "Argument helper failed: $($child.ExitCode)" }
    $actual = @([IO.File]::ReadAllLines($stdout) | ForEach-Object {
        [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_))
    })
    if ($actual.Count -ne $expected.Count) {
        throw "Argument count changed: expected $($expected.Count), received $($actual.Count). Values: $($actual | ConvertTo-Json -Compress)"
    }
    for ($i = 0; $i -lt $expected.Count; $i++) {
        if ($actual[$i] -cne $expected[$i]) {
            throw "Argument $i changed: expected <$($expected[$i])>, received <$($actual[$i])>."
        }
    }
    Write-Host "PASS: all $($expected.Count) native arguments preserved on PowerShell $($PSVersionTable.PSVersion)."
} finally {
    # Only the helper's flat scratch files are removed; no recursive deletion.
    Get-ChildItem -LiteralPath $scratch -File | Remove-Item -Force
    Remove-Item -LiteralPath $scratch -Force
}

[CmdletBinding()]
param(
  [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
  [string[]]$CliArguments
)

$ErrorActionPreference = 'Stop'

# Process-scoped overlay only: the repository .env and existing Ornith/LM
# Studio routes are not edited. This invokes the existing REV:N CLI/router.
$env:REVN_BRAIN_MODE = 'local'
$env:REVN_BRAIN_ENDPOINT = 'http://127.0.0.1:8826/v1'
$env:REVN_BRAIN_MODEL = 'qwen3.8-flash-next'
$env:REVN_BRAIN_MODEL_FILE = 'C:\AI\models\rocmfp4\Qwen3.8-Flash-Next-ROCmFP4-FAST-v2-ple16.gguf'
$env:REVN_BRAIN_CONTEXT = '65536'
$env:REVN_BRAIN_REASONING_EFFORT = 'medium'
$env:REVN_BRAIN_TIMEOUT_MS = '600000'
$env:REVN_BRAIN_MAX_RETRIES = '0'

& pnpm.cmd revn @CliArguments
exit $LASTEXITCODE

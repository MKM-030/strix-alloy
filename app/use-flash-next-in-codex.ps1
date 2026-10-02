$ErrorActionPreference = 'Stop'
$CodexArguments = $args
$projectRoot = Split-Path -Parent $PSScriptRoot
$catalogPath = Join-Path $projectRoot 'config/flash-next-model-catalog.json'
$codexRoot = Join-Path $env:LOCALAPPDATA 'OpenAI/Codex/bin'
$codexBinary = Get-ChildItem -Path (Join-Path $codexRoot '*/codex.exe') -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $codexBinary) {
    throw 'Codex is not installed in its usual Windows location.'
}

try {
    $models = Invoke-RestMethod -Uri 'http://127.0.0.1:8826/v1/models' -TimeoutSec 5
    if ('Qwen3.8-Flash-Next' -notin @($models.data.id)) {
        throw 'Flash Next is not the model served on port 8826.'
    }
} catch {
    throw 'Start the Strix Alloy Flash Next desktop shortcut and wait until the model is ready, then open this launcher again.'
}

$catalogPath = $catalogPath.Replace('\', '/')
$options = @(
    '--model', 'Qwen3.8-Flash-Next',
    '-c', 'review_model=Qwen3.8-Flash-Next',
    '-c', 'model_provider=strix_alloy',
    '-c', ('model_catalog_json=' + $catalogPath),
    '-c', 'model_context_window=32768',
    '-c', 'model_auto_compact_token_limit=24576',
    '-c', 'model_reasoning_effort=low',
    '-c', 'model_reasoning_summary=none',
    '-c', 'web_search=disabled',
    '-c', 'features.apps=false',
    '-c', 'features.plugins=false',
    '-c', 'features.hooks=false',
    '-c', 'features.goals=false',
    '-c', 'features.multi_agent=false',
    '-c', 'features.code_mode=false',
    '-c', 'features.code_mode_only=false',
    '-c', 'mcp_servers.node_repl.enabled=false',
    '-c', 'model_providers.strix_alloy.name=Strix Alloy Flash Next',
    '-c', 'model_providers.strix_alloy.base_url=http://127.0.0.1:8826/v1',
    '-c', 'model_providers.strix_alloy.wire_api=responses',
    '-c', 'model_providers.strix_alloy.requires_openai_auth=false',
    '-c', 'model_providers.strix_alloy.supports_websockets=false',
    '-c', 'model_providers.strix_alloy.request_max_retries=1',
    '-c', 'model_providers.strix_alloy.stream_max_retries=1',
    '-c', 'model_providers.strix_alloy.stream_idle_timeout_ms=300000'
)

& $codexBinary.FullName @options @CodexArguments
exit $LASTEXITCODE

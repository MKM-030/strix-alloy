# Portable host configuration

The native launcher selects operator-owned configuration explicitly. These source changes do not install models, create credentials, change an existing local configuration or restart running processes. Python services and model files are deployed separately from ServiceNow update sets.

## Before the next launch

- Set the Bot bridge's settings.instance_url, or SCC_VOICE_INSTANCE_URL, to the target ServiceNow HTTPS origin. Missing values fail closed when ServiceNow is enabled. Use voice/bridge.community.example.json as the blank starting point and provision identity, inbound integration and credential files locally.
- Select the Bot JSON with -BotConfig / --bot-config / SCC_VOICE_BOT_CONFIG and the native JSON with -NativeConfig / --native-config / SCC_VOICE_NATIVE_CONFIG. Unspecified paths resolve to voice/bridge.local.json and voice/native-bridge/config.local.json under the selected repository; example files are never activated implicitly. Relative selected paths resolve from the repository root. Both files must exist before the voice services start.
- Configure the native JSON for the target instance, assistant and agent. The launcher retains ServiceNow authentication checks and refuses development credentials. Start with voice/native-bridge/config.community.example.json, then configure and validate the target policy before enabling SDK access.
- Set -Origin / --origin / SCC_VOICE_STUDIO_ORIGIN to the public HTTPS origin that serves Studio. There is no source-host fallback. HTTPS is still required, including for loopback origins; binding remains 127.0.0.1. Credentials, paths, queries, fragments and ambiguous numeric hosts are rejected. Host case, one root slash and default port 443 are canonicalized to the browser's origin. The server keeps exact Origin and CSRF checks. The PowerShell Open action uses the URL returned by the same configured launcher.
- -PythonExecutable / SCC_VOICE_PYTHON selects the wrapper's Python interpreter; the default is the repository's voice/native-bridge/.venv/Scripts/python.exe. The native PowerShell wrapper resolves the selected interpreter before changing directory. Its child-service Python remains the repository's native virtual environment.

For an operator-prepared target profile, run from the repository root:

    $env:SCC_VOICE_STUDIO_ORIGIN = 'https://voice.customer.example'
    .\voice\Start-VoiceStudio.ps1 -Action Status
    .\voice\Start-NativeVoice.ps1 -Action Voice -BotConfig '.\voice\bridge.local.json' -NativeConfig '.\voice\native-bridge\config.local.json'

The hostname and local files above are placeholders for the target deployment.

Explicit CLI selections take precedence over environment values. Missing/empty Studio origins and missing selected configs fail before starting the corresponding service. Existing listener executable/argument checks, no automatic restart behavior, model ownership locks, recording retention and voice selection are unchanged. Existing all-action sequencing still reaches the voice configuration check after the speech/model/gateway phases; validate all operator profiles before requesting All.

## Operator choices still required

This is not a standalone host installer. The inspected deployment still needs a coordinated speech/model profile:

- voice/native-speech-validation/speech_probe.py contains five deployment paths: ASR executable/model and TTS executable/model/codec. stack_status.py separately validates the two executable identities. Configure these together in a reviewed follow-up profile; changing just one side causes strict ownership/status checks to fail. The optional validation audio fixture is also installation-specific. Do not bundle recordings or assume the original machine's C:/AI or E: paths.
- The Halogen deployment descriptor, model files, reviewed profile hashes, gateway settings and gateway receipt interpreter identity remain deployment-specific. This change does not alter model versions, cache/memory settings or their provenance checks. start_services.py retains the old gateway receipt interpreter pin until it can be derived from the reviewed deployment binding.
- Legacy CPU/browser launchers Start-Voice.ps1 and Start-MobileVoice.ps1, Configure-Voice.ps1 and existing installed shortcuts still need their own operator path/origin configuration. They are not the native launcher and are not a portable installation route. Do not use them to start the deprecated CPU speech workers alongside the native services.

Provision matching DNS/TLS/public routing, callback registration and token files on the target host/instance. A fresh-host installation and physical-device acceptance remain required after that deployment-specific configuration; source tests alone do not establish them.

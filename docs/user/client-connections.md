# Connect Flash-Next to your applications

Start **Strix Alloy - Flash-Next** from the desktop and wait for the server to say
`ready`. Keep its window open while using the model. The shortcut starts an ordinary
`llama-server` with the existing GGUF files and shared MTP draft sidecar. The sidecar
helps generate tokens faster; clients select only the main model.

Use these connection fields:

| Field | Value |
| --- | --- |
| Provider / API format | OpenAI-compatible **Chat Completions** |
| Base URL | `http://127.0.0.1:8826/v1` |
| Model ID | `Qwen3.8-Flash-Next` |
| API key | **`local`** in ZCode; leave empty in clients that allow it |
| Context window | `65536` on this desktop; `32768` with the portable script's defaults |
| Maximum output | Start with `4096` tokens or fewer |

The context window includes the conversation, tool definitions and generated answer.
Leave room for the answer; a larger output limit does not increase the loaded context.
The desktop shortcut uses `-ContextSize 65536 -Ubatch 8192`: ZCode's initial
instructions alone used 30,319 tokens in testing. The Codex launcher keeps a
conservative 32,768-token client budget within that larger server allocation.
The **base URL excludes `/chat/completions`**: clients append that path themselves.
Use the model ID above, rather than a GGUF filename or a URL in the model field.

The built-in chat page is [http://127.0.0.1:8826](http://127.0.0.1:8826).
The launch script also accepts `-OpenBrowser` to open it when ready, including when
reusing an already running server. This is optional for API clients.

## Why the desktop launch failed

The `.cmd` entry point passed an unsupported `-agent` option to the PowerShell
launcher, which prevented startup. That option has been removed. No agent flag is
needed for model discovery, chat completions or a client's own tools. Some newer
llama.cpp builds offer `--agent` for their built-in tools and CORS proxy; that is a
different feature. `--embedding` means producing embedding vectors and is also
unrelated to connecting this chat model to another application.

## ZCode / Z AI

Use a custom OpenAI-compatible provider with the fields above, then select
`Qwen3.8-Flash-Next` for the conversation. Choose **Chat Completions**, rather than
the Anthropic Messages format. If the provider has a model discovery button, run it
after the server becomes ready.

On this machine, the existing authoritative ZCode provider already had the correct
URL, format and model ID. The failed server launch was the main connection problem.
ZCode also requires a nonempty API key to select this provider, even though the
server does not require authentication. Its saved Local provider has no key: enter
the harmless placeholder **`local`**. The installed ZCode client was verified with
that placeholder, the exact model ID and local URL, returning `ZCODE_LOCAL_OK`.
Automatic approval review blocked a persistent ZCode configuration change during
the investigation, so the placeholder was tested in an isolated configuration and
has **not** been saved to your regular ZCode provider. Enter it in ZCode's provider
settings before selecting the model.

The same first ZCode request took 66.3 seconds with the original 32k/2k serving
settings and 60.2 seconds with the desktop's 64k/8k settings. Prompt processing
fell from 61.7 to 54.6 seconds; both requests had 30,319 input tokens and no cached
input. These are single cold-request measurements, not a general speed guarantee.
Reducing unnecessary tools, plugins and attached context in ZCode can also reduce
the amount of text the model must process before answering.

## Unsloth Studio

The local installation now has an enabled connection named **Strix Alloy -
Flash-Next**, using the **llama.cpp** provider, the base URL above and the selected
model `Qwen3.8-Flash-Next`. Reopen or refresh Unsloth to synchronize its model picker.

To recreate it, open **Settings → Connections**, add **llama.cpp**, enter the base
URL, load the model list, select `Qwen3.8-Flash-Next`, and save. No API key or second
model load is needed. This uses the already running Strix Alloy engine and its
sidecar. Unsloth's own GGUF loader is a separate option with a different runtime
and settings; switching to it requires separate performance validation.

Verified on 19 September 2026 with the installed Unsloth adapter: discovery returned
the model ID, and a streamed request returned “Strix Alloy connected through
Unsloth.” with a completed stream and no errors. Server statistics showed active
MTP drafting. The native desktop picker was not visually verified. See the
[Unsloth investigation](../benchmarks/unsloth-integration-research-20260919.md) for
versions, update findings and the distinction between connection and speed tests.

## Codex

Start the model, then open **`app/Use Flash Next in Codex.cmd`**. This launches the
installed Codex command-line application with the local model selected for that
run. It also accepts ordinary Codex arguments, such as a working-directory option.
It does not change your saved provider or default model.

Codex uses the **Responses API**. Full client testing initially exposed two issues:
the model's strict template rejected later system instructions, and the server did
not accept Codex's namespace tools. The launcher now supplies a compatible chat
template and a model catalog using standard function tools. System/developer
instructions are combined in their original order; normal chat and tool history
rendering are unchanged. `-UseModelTemplate` restores the original strict template
for diagnostics.

The actual Codex client was verified with an exact-answer request and a file-read
task: it invoked PowerShell, read a local fixture, and returned the correct value.
This local mode supports the tested shell-tool workflow. Apps, plugins, hooks,
multi-agent mode, code mode and built-in web search are disabled for this invocation
because their tool formats are not all supported by the server. It is not a claim
of feature parity with the hosted Codex models.

Automatic approval review blocked installing a saved Codex profile, so no model
picker/default-provider registration was made in the desktop app. The working
launcher is the available route. For manual configuration, the repository has
`config/flash-next.config.toml` and `config/flash-next-model-catalog.json`; the profile's
catalog path must point to the actual file. The installed Codex version supports
separate `$CODEX_HOME/<name>.config.toml` profile files selected by `--profile <name>`.

## If the model is missing

Open [the model list](http://127.0.0.1:8826/v1/models). It should include
`Qwen3.8-Flash-Next`. If the page cannot connect, start the desktop shortcut and
check its window for an error or wait for loading to finish. If the list works,
recheck the client's base URL, API format and exact model ID, then refresh its model
list. A cloud-hosted application cannot reach this computer's `localhost`; use a
client running on this PC for this local-only setup.

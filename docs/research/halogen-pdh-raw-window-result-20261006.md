# Fresh GPU PDH epoch — 2026-10-06

The source compiles with MSVC `/W4 /WX /O2`. One bounded idle runtime check
opened, collected and closed its owned PDH query successfully, but the wrapper
rejected the baseline before acknowledgement. No model request or server
lifecycle operation occurred.

The raw wildcard returned 358 entries. Eight VM engine names each appeared twice.
Pairing by enumeration position or treating those duplicates as zero activity
would discard identity ambiguity, so neither occurred. The owned marker produced
a final collection and terminal receipt; the wrapper closed its owned job.
The minimum recorded physical reserve was about 25.74 GiB. The original
HistoricalStock foreground server remained running.

The root tool token is currently not an administrator token. Direct process-handle
queries for the VM worker and vmmemWSL returned access denied; the readable
wslhost processes do not establish the missing identities.

Microsoft documents a supported sequence for English wildcard counters:
obtain the localized full path, expand it, then add each explicit counter path.
This is the next software correction to assess. Its indexed paths identify
counter instances; they do not establish guest ownership or process generations.
[PdhAddEnglishCounterW](https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhaddenglishcounterw),
[PdhExpandWildCardPathW](https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhexpandwildcardpathw).

The [JSON receipt](halogen-pdh-raw-window-result-20261006.json) pins the build,
raw arrays and failed coverage receipt. The old comparison remains unqualified.
There are no new Prefill, Decode, acceptance or NPU throughput values from this
check. Do not repeat the raw wildcard test unchanged.

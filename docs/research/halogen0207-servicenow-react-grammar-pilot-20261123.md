# Halogen 0.20.7 strict grammar pilot for ServiceNow ReAct

Forcing an inert function enabled native grammar drafting on the repository's
synthetic SCC name-confirmation fixture. The forced response accepted 28 of
30 grammar drafts. The normal typed JSON response recorded zero grammar
drafts. Both responses asked for confirmation, but their parsed Action and
Thought fields differed. The pilot stopped before the measured cohort.

| Format | Actual input / output tokens | API Prefill tok/s | API Decode tok/s | MTP head accepted/drafted | Windows HTTP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Typed JSON | 2,826 / 230 | 964.67 | 55.68 | 166/191 (86.91%) | 7.339 s |
| Strict forced function | 3,359 / 174 | 1,834.82 | 57.06 | 94/121 (77.69%) | 4.983 s |

There was one request per arm with identical input messages and JSON Schema.
The native template inserted different format instructions. The forced request
used 533 more input tokens and generated 56 fewer output tokens. The pilot
does not attribute the difference in HTTP time to grammar drafting. The phase
rates come from the unadjusted native API fields.

The private collector unwrapped the forced call's arguments and validated the
confirmation before accepting the response. It recorded the proposed call
without executing it or contacting ServiceNow. The regular 32K Halogen
0.20.7 instance handled both requests without a restart. The live ServiceNow
response transformer still expects typed JSON.

The corrected run, raw events and independent Windows QPC timing are retained
under `server/.local/halogen-update-20261122/primary0207/react-forced-tool-shadow-v1/react-pilot-v2`.

| Evidence | SHA-256 |
| --- | --- |
| Typed JSON sample | `fdeebe2f032b81a6dac89e8811d986608c57ffdd162df610f32da24974ab3d3b` |
| Forced function sample | `aa7435b405fe1c521cbfdb1d2ba71a121a75cd89ecc0bdd1983c7a62962a2e18` |
| Terminal handle | `95faac383d75680cb9b541e32f8b3cb03ca2b738e323b93d88b372a36059c90b` |

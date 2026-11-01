# ServiceNow chat reconciliation

Revision: 28 October 2026. This audit identifies the final executed capability-based copy script, reconciles dated outcomes from the related chats, and records the evidence limits before legacy chats are archived. It introduces no ServiceNow or runtime changes.

The starting label “ServiceNow AI Configurations” resolves in the available inventory to **ServiceNow AI Skill Configuration**. That conversation explicitly names **ServiceNow-Chat-Übergabe fortsetzen**, **Erstelle vollständige ServiceNow-Dok**, **ServiceNow Voice Übergabe**, and **ServiceNow Voice Implementierung**. The first is the current central consolidation thread and remains open. The private reference graph distinguishes those explicit references from related sources identified by the earlier documentation audit.

## Evidence and source coverage

The audit preserved redacted recent reads of the related ChatGPT conversations, the earlier 15-page review covering 106 turns, and additional later Voice implementation and handoff messages. Durable backing identities were matched to their ChatGPT aliases through retained provenance and matching user messages. These identities are recorded privately rather than treated as extra independent source chats.

The original configuration conversation was also read through its rendered chat UI, loading older messages back to its first message on 27 October at 11:05. This recovered the explicit four-chat reference that the recent-turn reader omitted. The documentation thread's complete local message and compaction extracts were preserved when an oversized older turn prevented further connector pagination. The current central thread's full messages and rollout were not read.

| Exact source title | Reconciled contribution | Status or limit |
| --- | --- | --- |
| ServiceNow Strix Einrichtung | Initial Halogen request/response integration. | An early adapter setup, not acceptance of the later combined system. |
| JavaScript Namen dynamisch anpassen | Standalone definition/prompt graph copier, then the `CustomLLMCapabilityManager` design and UI actions. | The standalone copy was revised afterward; the manager was a proposal with local tests, not established native installation. |
| JavaScript IDs iterieren | Iteration over the supplied capability list. | Explains the earlier 37-capability input; it is not the final 14-capability delta. |
| Skript anpassen | Executed capability conversion and related-list metadata copy; subsequent Voice work. | Historical 37-capability and provider-template results must not replace later validator and computed-field corrections. |
| ServiceNow Voice LLM Prüfung | Separation of capability/provider setup from the native Voice provider contract. | Custom text skills working did not prove that the native Voice runtime accepted the same provider. |
| ServiceNow Tabelle finden | Dictionary-aware validator linking, final copy delta, and Incident summary response correction. | The final executed source is recovered separately; neither an earlier code block nor a manager proposal substitutes for it. |
| ServiceNow Voice Implementierung | Browser Voice, local speech/model integration, and later native Mobile adapter work. | Dated successful server audio tests coexist with later device failures and model availability problems. |
| ServiceNow Voice Übergabe | Android/iPhone SDK fixes, model migration, prompt parameter forwarding, and the 812-version baseline. | Its later user reports and diagnostics still show device regressions; see the dated sequence below. |
| ServiceNow Übergabe fortsetzen | Analysis of completion events arriving before response text, plus failed follow-up calls. | Eleven regression tests were reported for a prepared fix; the final source message says deployment was blocked and HTTP 503 remained separate. |
| Erstelle vollständige ServiceNow-Dok | Native historical script audit, installed prompt mirror evidence, transport preparation, and dated handoffs. | Its 27 October missing-repair-capture conclusion is superseded by the 28 October native candidate export. |
| ServiceNow AI Skill Configuration | Model-picker diagnosis, preservation of Gemma behavior, restoration of the custom SCC Vision dispatch, and the final repair log. | Resolver/database verification succeeded; the log explicitly retains `live_skill_tested=false`. |
| Add Antragsformular Use Case | Related Vision/catalog example and its UI entry points. | A separate related project owner; excluded from the legacy source-chat archival candidates. |

The already archived **Messe-Stimmen bereinigen prüfen** run supplies dated retention-cleanup evidence only. It is not an instruction to repeat cleanup, restore recordings, or transport voice recordings.

## The final executed capability-based copier

The missing final source is now preserved with its original provenance in the [capability prompt copy guide](capability-prompt-copy.md) and [source manifest](../../servicenow/byollm/capability-prompt-copy/SOURCE-MANIFEST.json).

The exact historical script is **38,034 characters**, SHA-256 `dc390ee11c3abfb71d8f4bcd252b2ff9bfa92b93b92bd844a69ca27787e25db2`. Native script history dates it to **13 October 2026, 16:20:31 UTC**. Its actual input contains **14 capability IDs**, despite an older comment referring to 37.

The recorded final repeat returned:

```json
{
  "ok": true,
  "capabilities": 14,
  "writes": 0,
  "unchanged": 292,
  "validatorLinksInserted": 0,
  "validatorLinksSkipped": 13
}
```

Its decisive correction excludes computed `sys_generative_ai_config.request_tokens` both when copying and when checking for changes. The preceding read-only diagnostic reported 59 differences in that field; earlier copy variants consequently reported writes on otherwise equivalent configurations.

This is a **capability-based supporting-graph copy**, preserving the existing capability/skill identity. It prepares the provider definition, definition configuration, AI/prompt configurations and relevant relations; it does not create cloned skill identities. It discovers the actual request/response validator ownership fields from the dictionary and references validator programs. On the examined source, request ownership includes `document_table`, `document_id` and `definition`; response ownership uses the `definition` Document ID without a `document_table` field.

The historical copier can change provider defaults after saving its graph. It also uses `setWorkflow(false)`, source-specific model/flow/alias values, and the historical per-scope capture approach. Its error handling restores changed defaults best-effort rather than rolling back every copied record. Preserve it as executed evidence; review the guide before considering any reuse.

The installed later [prompt mirror](prompt-mirror.md) is a separate implementation. Its native generators, state ownership, write gates and preservation of active provider selection must not be replaced by the old copier's behavior. Neither `CustomLLMCapabilityManager` nor the later `CustomLLMManager` proposal is the identity of that installed mirror.

## Dated outcomes that must stay separate

**13 October — Incident summarization.** The source reports that the intended model was reached but the output was rendered as characters from `undefined`. The executed repair supplied a suitable JSON-text-array validator rather than assuming `model_output` existed. A later shortened validator name corrected a field-length/adoption issue, and an unchanged repeat reported zero writes. This is a specific validator contract correction, not justification for a global response wrapper.

**18 October — device success and subsequent model migration.** The Voice handoff records the iOS SDK HTTP-200 correction, followed by the user's confirmation that Android and iPhone worked. A later memory failure and restoration belong to a different incident. The earlier Gemma documentation handoff then recorded local readiness while native selection remained blocked. Later that day, **ServiceNow Voice Übergabe** reported **187 skill configurations switched, 189 completed changes**, a successful native model test and OneExtend generation. That later dated result supersedes the earlier blocked migration status for that release. It does not establish every device or target route afterward.

**19 October — parameters, baseline and regressions.** The handoff subsequently reports Voice instructions/languages forwarded to the actual prompt and the consolidated **31-set, 812-CU-version** baseline. Later Android/iPhone tests again failed during audio establishment; some calls produced only a greeting. The next continuation identified response text arriving after a completion event and reported HTTP 503 on subsequent calls. Its final message explicitly says the tested response fix was not deployed because the remote access quota blocked the attempt. These failures are not erased by the earlier device or model-migration successes.

**27 October — model-picker and Vision repair.** An initial visibility-only change did not remove ambiguous mapping resolution. Later evidence corrected the earlier diagnosis that the SCC example merely needed a standard Vision flag: it used a custom `SCCVisionRequestTransformer` dispatch. The final pasted log confirms mapping/transformer updates, deletion of the duplicate mapping, matching batch/single resolution and both active models, while retaining `live_skill_tested=false`. Gemma's existing Voice/business behavior was preserved.

**28 October — source candidate export.** The native parent and all **36 unique sets are Complete**, with **868 Customer Update versions** in the downloaded XML. The final review verified six source-equal code fields across four records, including preserved Gemma logic. This supersedes the older “repair capture missing” conclusion. The [batch status](batch-status.md) and [transport runbook](transport-runbook.md) remain authoritative for the exact exported artifact and target dispositions.

## Remaining boundaries and archival readiness

The final audit has 15 scope/container differences, including a composite UI section; every CU application matches its payload scope. The old Greeting and new Global Halogen copies have identical full payloads. Prefer the Global container and resolve the duplicate during native target preview; container placement alone does not make the script invalid.

The current SCC Vision helper is captured, but its historical referenced AI configuration is absent from the public export. Its private/example graph remains a prerequisite. The export contains neither ACT routing-selection rows nor any `sys_properties` rows. ACT policy and all four mirror properties require explicit target-local administration; fail-closed helper defaults do not prove that those properties exist.

Fresh target preview/import, complete dependency closure, approved security/deletion decisions, and selected text/Vision/Voice/agent acceptance remain unproven. Historical tests, assistant completion claims and a successful source export are separate evidence categories.

The private audit contains an exact **11-chat archival list** with returned titles, IDs, source/kind and backing aliases. It excludes the current central thread, unrelated runtime/project owners, the separate Vision project owner, and the already archived cleanup run. After final artifact and documentation verification, the central task archived all **11 legacy source chats on 1 November 2026**; each archive call returned `archived=true`. The current central task and the excluded owners remain available. The read-only audit itself performed no archival; its original candidate inventory remains unchanged, with a separate final archive-results receipt.

Reader limits remain explicit: long chat items can be truncated at 20,000 characters; retained historical tool responses and arguments are not uniformly available; selected UI extracts are not a byte-identical full chat export. The exact final copier is supported by its separate native-history source and provenance, so no executable code was reconstructed from truncated chat text.

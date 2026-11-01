# ServiceNow BYOLLM documentation and release hub

This is the canonical entry point for the BYOLLM platform configuration, Community article and consolidated ServiceNow release work. The source worktree is the existing primary checkout; historical task workspaces are evidence archives, not alternate current implementations.

## Start here

- [Technical documentation](master-manual.md) and [quickstart](quickstart.md): the consolidated English procedure, including the findings from the documentation and AI Skill Configuration chats.
- [Final executed capability-based prompt copier](capability-prompt-copy.md): the exact final script, its configuration and the successful 14-capability repetition evidence.
- [Existing-skill prompt preparation](prompt-mirror.md): the installed shared helper, eight Business Rules and manual backfill script, without cloning skills.
- [Community article draft](community-post.md): the English publication draft, with clear boundaries between governance, model registration, prompts and runtime selection.
- [Screenshot checklist](screenshots.md): what each author-supplied image should demonstrate.
- [Configuration boundaries](configuration-boundaries.md): supported product controls, observed technical tables and release-dependent limitations.
- [Consolidated batch status](batch-status.md): baseline, current deltas, transport boundaries and target acceptance.
- [Final release verification](release-verification.md): exact delivery hash, complete native readback and the five unresolved source-preview findings.
- [Later Halogen Agent delta audit](../../servicenow/byollm/halogen-agents-20261101/POSTRUN.md): 1 November's completed source maintenance and verified no-delete 69-CU WIP capture. All 68 intended sources match; the holding set is empty/ignored. This delta remains separate from the sealed 2.2 fresh-instance delivery; phone/runtime and target-import acceptance remain distinct.
- [Transport coverage](transport-coverage.md) and [target installation runbook](transport-runbook.md): platform-wide coverage, preview decisions and target-local prerequisites.
- [Sources and prior documentation](sources.md): official references and the reconciliation of earlier documentation approaches.
- [AI Agents article](ai-agents-follow-up.md) and [AI Voice article](ai-voice-follow-up.md): two full English companion drafts. Together with the general overview, these form exactly three articles; publication URLs and author screenshots remain pending.

## Canonical implementation and evidence

[Native own-source files and field ledger](../../servicenow/byollm/README.md) provide the verified implementation sources. The existing [Voice 2.0 installation guide](../local-voice/NEUINSTANZ-INSTALLATION-DE.md), [parameter matrix](../local-voice/parameter-matrix-current.json) and [code-field hashes](../local-voice/final-source-hashes.json) remain detailed historical release references.

The current consolidated release starts with the six-family Voice 2.0 native batch: 31 unique sets, 812 Customer Update versions and 783 unique names. Later host/runtime work is separate from ServiceNow transport metadata. Newer native deltas must be assessed and captured explicitly; a repeated export of the old batch does not prove that all later changes are included.

The target delivery is **Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028**: 809 unique INSERT_OR_UPDATE records, with no outer or embedded deletion actions and no insert/delete conflicts. It is an explicitly derived fresh-instance package, with one selected final version per update name. The unchanged 868-version native 2.1 export and later notice-language export remain provenance inputs. See [batch status](batch-status.md) for the delivery contract, native loader/preview evidence and target prerequisites.

Original exports, full evidence paths and older article drafts are retained in ignored local storage with separate 27 and 28 October manifests. The newer archive adds revised documentation and AI Skill Configuration evidence without overwriting the originals. These are not attachments for automatic public release. A completed source batch does not establish successful preview or import on a compatible target instance.

The [referenced-chat reconciliation](chat-reconciliation.md) records the recovered final script, dated runtime findings, references and retrieval limits. This task is the central continuation after legacy source-chat archival.

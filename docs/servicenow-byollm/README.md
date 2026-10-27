# ServiceNow BYOLLM documentation and release hub

This is the canonical entry point for the BYOLLM platform configuration, Community article and consolidated ServiceNow release work. The source worktree is the existing primary checkout; historical task workspaces are evidence archives, not alternate current implementations.

## Start here

- [Community article draft](community-post.md): the English publication draft, with clear boundaries between governance, model registration, prompts and runtime selection.
- [Screenshot checklist](screenshots.md): what each author-supplied image should demonstrate.
- [Configuration boundaries](configuration-boundaries.md): supported product controls, observed technical tables and release-dependent limitations.
- [Consolidated batch status](batch-status.md): baseline, current deltas, transport boundaries and target acceptance.
- [Sources and prior documentation](sources.md): official references and the reconciliation of earlier documentation approaches.
- [AI Agents follow-up brief](ai-agents-follow-up.md) and [AI Voice follow-up brief](ai-voice-follow-up.md): planned separate articles, not published Community URLs.

## Canonical implementation and evidence

[Native own-source files and field ledger](../../servicenow/byollm/README.md) provide the verified implementation sources. The existing [Voice 2.0 installation guide](../local-voice/NEUINSTANZ-INSTALLATION-DE.md), [parameter matrix](../local-voice/parameter-matrix-current.json) and [code-field hashes](../local-voice/final-source-hashes.json) remain detailed historical release references.

The current consolidated release starts with the six-family Voice 2.0 native batch: 31 unique sets, 812 Customer Update versions and 783 unique names. Later host/runtime work is separate from ServiceNow transport metadata. Newer native deltas must be assessed and captured explicitly; a repeated export of the old batch does not prove that all later changes are included.

The 27 October working 2.1 parent now groups 36 native sets in four direct branches, including the preserved baseline, the later Greeting Context Fix, the existing custom-skill/context branch and a fresh three-record Global context delta. It remains In progress. See [batch status](batch-status.md) for counts, remaining transport decisions and the distinction between source consolidation and target acceptance.

Original exports, full evidence paths and older article drafts are retained in ignored `server/.local/byollm-consolidation-20261027` storage with hashes. They are not attachments for automatic public release. A completed source batch does not establish successful preview or import on a compatible target instance.

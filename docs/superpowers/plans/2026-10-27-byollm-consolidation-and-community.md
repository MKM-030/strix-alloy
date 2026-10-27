# BYOLLM consolidation and Community article plan

The user requests one central worktree and documentation approach, continued consolidation into one ServiceNow batch, and an English Community article. Screenshots will be supplied by the author. AI Agents and AI Voice receive separate linked follow-up articles.

## Scope and decisions

- Keep `C:/Projects/strix-alloy-clean` as the only source worktree. Do not recreate retired checkouts or move active external model, voice or DLL assets.
- Preserve historical exports and evidence. Consolidate verified final native source fields, current documentation and an immutable artifact inventory. Private release files and historical drafts stay in ignored local storage.
- Start from the actual six-family Voice 2.0 release, not the superseded 120-CU or 293+17 checkpoints. A fresh browser export currently reproduces all 812 historical payload versions, while newer live customer updates require a separate delta assessment.
- Use the authenticated ServiceNow browser for native batch operations. SDK credentials are absent; no credential-store inspection, authentication automation, or alternate-token use.
- Keep provider policy, technical model registration, skill prompts, Admin routing, agent engine support and audio infrastructure distinct. Existing provider policy is observed, not changed: only Custom LLM Provider; fallback off; global routing.
- Preserve the loaded Halogen and own TTS. No model/service operations, microphone, inference, business action, security-policy bypass or automatic provider activation is part of this task.
- Prepare the article for the user to publish. Do not publish it or expose private exports, tenant identifiers or credentials.

## Tasks

1. Verify the central Git/worktree state and reconcile prior documentation, export versions and own source hashes.
2. Copy final own native sources into `servicenow/byollm`, with all available code-field hashes and explicit provenance. Keep private evidence and prior drafts under `server/.local/byollm-consolidation-20261027`.
3. Inspect native batch membership and post-19-October deltas. Preserve the completed baseline. Consolidate only exact reviewed owned metadata through native update-set hierarchy/capture operations; distinguish source export from target-import acceptance.
4. Write `docs/servicenow-byollm/README.md`, configuration boundaries, batch state and source notes. Point older entry points at this canonical index without rewriting historical evidence.
5. Draft the English Community article at 1,500–1,900 words, with a screenshot checklist and clearly marked links to planned Agent and Voice articles. Verify technical claims against versioned official documentation and current observed table fields.
6. Validate copied source/artifact hashes, internal links, article length and public-content privacy. Review the article independently. Do not rerun unrelated model or service tests.
7. Deliver the canonical article and batch evidence, and state any native/target validation still open.

## Completion criteria

One canonical source/documentation index, preserved historical artifacts, a truthful current batch manifest and native state, a reviewed English article with screenshot instructions, and no runtime or provider-policy change.

## Delivered 27 October

The existing primary checkout is the sole Git worktree. The canonical hub and seven supporting English documents, the 17-field source snapshot, prior-documentation banners and private evidence archive are consolidated there. The Community overview is approximately 1,800 words, has seven screenshot markers, and links to separate planned AI Agent and AI Voice articles. Independent technical and editorial reviews found no remaining concrete article issues after corrections.

The native 2.1 working parent groups 36 sets in four direct branches. The 31-set completed 2.0 baseline is preserved, the two later existing branches are linked, and three current Global context records are captured in a dedicated child. Native observations show 31 Complete and five In progress sets; their observed branch CU counts total 849 versions. No full completed 2.1 export or target import is claimed. Current-source coverage, scope/dependency and security review, target binding/preview/import and runtime acceptance remain release gates in `docs/servicenow-byollm/batch-status.md`.

Fresh local verification confirmed all 17 source-field hashes and 74 unchanged original/archive files, one worktree, no broken canonical relative links, no public-content privacy findings, and a clean whitespace check. Native hierarchy, payloads, restored context and screenshot evidence are retained in ignored local storage. No model, speech service, provider routing or business execution was changed.

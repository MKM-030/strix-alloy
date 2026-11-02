# Voice entry context repair — investigation and design boundary

Marcel asked for autonomous repair of the complete Voice flow and explicitly
delegated implementation decisions. This document records Root's design choices;
it does not represent a separate user approval or a completed native change.

The configured welcome and independent conversation are active. The separate
VA Input and two default Planner model assignments now use Halogen; the latest
actual conversation records six successful Halogen calls. The remaining native
failure happens after model output. `AgentReActivePlannerUtil` cannot obtain a
needed subtask/cache value. Independently, the initial execution plan and its
first subtask both contain the literal objective `undefined`, before any name
confirmation. These facts must not be conflated into a fully proved causal chain.

The current entry ID is a promoted standalone agent skill, not a VA topic ID.
Native `InvokerUtil.initializeForNonStudio` obtains a task from native VA
variables or search text. Its configured objective fallback applies only when
a usecase is already selected. The current direct skill route has no such
binding. Bot context variables belong to `vaContext`; inventing a mapping into
`vaVars.global_objective` would not satisfy that consumer.

Approaches considered:

- Supply arbitrary client context/task text. Rejected: no proved native input
  mapping, and a recognized name must not become an invented business objective.
- Add an owned VA initializer topic that binds centrally configured workflow
  information and delegates to the native invoker. Possible, but adds a custom
  entry topic and its publication/routing maintenance.
- Use a native centrally configured promoted workflow containing the existing
  SCC agent, with a real configured objective and the same access boundaries.
  Root's preferred direction, subject to confirming native creation/promotion
  contracts and the subtask/cache relationship. No existing visible SCC workflow
  was found in the current native read-only lookup.

Keep the agent, tools, Skill Kit/ACT authority, local model, own TTS and ASR.
Do not edit vendor scripts, existing roles/ACLs or user role assignments,
broaden visibility, replay completed installers, or assume a newly created
workflow will fix every downstream error. Prepare exact owned metadata,
capture and reversal evidence before applying.

The actual modern AIUX form differs from the classic guided setup. Normal
Save requires roles and creates own execute ACLs, their admin-role links,
and a dynamic-user data-access configuration. Actual Save created one proper
workflow ACL and one admin link; no redundant agent ACL is added. These are additional security
records, beyond the already approved model corrections. Marcel explicitly
approved the complete finite V4 workflow/security/profile/test scope on
2 November; no second model or plan approval is required. The selection preserves the
existing SCC restrictions: caller role `admin`, approved data roles `itil`
and `scc_voice_context_reader`, and only the existing SCC agent. No role is
granted to any user. The new distinct name is `SCC Laptop Onboarding Voice Workflow`.

Native Save creates a published V1 and an active backend configuration; it is
not a draft. Channels remain off until separately verified promotion to the
one existing Voice profile. The exact modern source manifest and action-time
approval were recorded before the one native Save.
Global ownership, capture, the published ReActive Planner strategy and the
central objective property must be verified before any Voice entry change.

Acceptance requires an actual supported entry with a nonempty configured
objective, correct agent identity, successful same-name continuation without
automatic retry, no unintended business action, current source-bound output,
and acknowledged cleanup. The observed 40-second waits and canonical error
remain failed results. A new probe must reject those error/retry messages
immediately and retain all name binding, full TTS drain and input limits.

Physical device, public-network and full context/progress acceptance remain
separate. No new model or speech-service lifecycle action is needed for this
metadata investigation.

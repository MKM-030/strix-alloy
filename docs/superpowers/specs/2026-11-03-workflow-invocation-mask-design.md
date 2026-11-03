# Workflow child invocation mask repair

Both actual access-verification outputs now show the same precise failure:
the fixed workflow passes its invoke ACL, its original SCC child fails. Evidence
is background-workflow-actual-chain/08-exact-access-verification.private.json
and 09-prior-v7-access-verification.private.json under the private repair root.
This supersedes the assumption that guest log context alone identified the sole
cause. It does not prove all authentication and device behavior is correct.

ServiceNow documents the sequence: workflow ACL, workflow role mask, child ACL,
child role mask, tool ACL. The workflow mask currently lacks admin, which the
existing original child invoke ACL requires. The exact native output and that
configuration explain the denied child without changing the business transport.

Primary documentation:
https://www.servicenow.com/docs/r/zurich/intelligent-experiences/acls-and-rolemasking.html
https://www.servicenow.com/docs/r/intelligent-experiences/enable-ai-experiences/aia-role-masking.html

## Selected smallest correction, subject to specific security approval

Add the existing admin role only to the OUTER workflow role mask. Preserve both
existing outer roles and both existing invoke ACLs. Preserve the original SCC
child's exact two-role mask. Do not add any user-role membership or switch to
an AI/service user. The outer orchestrator gains admin authority from invoking
administrators; this is an explicit expansion from the previously approved
outer two-role configuration, requiring concrete review before application.

Child/tool roles still narrow by intersection:
U ∩ {admin,itil,reader} ∩ {itil,reader} = U ∩ {itil,reader}.
Do not describe the outer change as no security change or a proven runtime
success. Verify native access and effective role behavior afterward.

Changing the child's invoke ACL would alter who can invoke the original agent.
Removing the outer mask would retain more roles than this one required role.
Neither is selected. Keep current B2B/Voice transport for the next changed test;
do not implement an extensive Background replacement for this mask defect.

## Exact operation

- Workflow 2f3c8a39931093185c8132d47aba1014.
- Outer mask 884cca39931093185c8132d47aba1082.
- Original child a4a9438393738354e7f2b9fa6aba101d.
- Child mask a6bc4f8393b38354e7f2b9fa6aba1022.
- Existing itil 282bf1fac6112285017366cb5f867469.
- Existing reader de69200f93485750e7f2b9fa6aba1043.
- Existing admin 2831a114c611228501d4ea6c309d626d.
- Public native operation:
  new global.AgentAccessRoleConfigDAO().updateAgentRoleConfig(outerId,
  {roleList:[itilId,readerId,adminId]}).

Its installed public, unprotected source is retained in
positive-name-after-planners-trace/AgentAccessRoleConfigDAO.native.private.js.
The native full-set delta preserves existing two mappings, creates one admin
mapping and updates the parent config's normal metadata/empty role_list. No
removal is expected. Do not call its private helper or the broader run-as broker.

Write a preview-first fix script plus injected local tests and a complete
execution review. Default behavior reads only. Before apply, require actual
nonguest non-impersonating admin, rhino.global AND current application global,
plus exact existing Global in-progress update-set identity/name matching both
preferences. Proposed capture name:
Custom LLM Voice 3.0 - Workflow Invoke Mask Repair - NO DELETE 20261103

Current Code app/set is not authorized creation context for this operation.
Use normal Global selection and a new ordinary WIP set after approval, then
read back their real identities; no denied namespace/scope overrides. The native
SDK call uses alias byollm-consolidation, scope global, rollback capture.

Before values, require ordinary domain-respecting row and all-field read rights;
exact role names/IDs, workflow/child linkage, active Dynamic-user overrides,
both masks, complete mapping sets and admin invoke ACLs must still agree.
No hidden rows may certify absence. Denial/drift refuses; no alternate privilege.
Re-read fresh preimages immediately before the one native public update.
Afterward independently compare both masks, original mapping IDs, both ACLs,
Dynamic-user configuration and native capture. Missing result/readback means
uncertain application, never permission to retry or roll back by deletion.

No service/model/audio/user input is part of this apply. No test/new start until
actual readback and a separate bounded changed-path test plan. Preserve every
executed probe, its source and receipts. Full Voice goal remains open.

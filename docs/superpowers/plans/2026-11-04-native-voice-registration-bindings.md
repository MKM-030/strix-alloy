# Explicit native voice registration bindings

Root-approved scope: manage_voice.py, start_services.py and offline tests only. No live registration, speech/model start, stop or restart. Keep scc-demo mapped through active.json and restore explicitly bound ServiceNow UUIDs independently of that mutable alias.

Use optional profiles/native-registrations.json with schema_version1 and a bounded registrations list. Each entry binds one canonical UUID to an immutable staged profile_id and exact reference_sha256. Read and revalidate the actual local profile, own-voice consent and WAV hash before any registration. Missing manifest means no extra mappings. Reject malformed/duplicate IDs, hash changes, foreign paths, and UUID collisions; never guess a vendor voice mapping. Binding metadata uses the existing activation_lock and cannot overwrite a conflicting UUID.

native_register retains the default scc-demo alias, adds an optional explicit voice_id and admits UUIDs only when their exact local manifest binding exists. Startup validates the complete plan before posting, restores alias plus bound UUIDs, and caches the exact plan together with TTS PID/create-time. Invalidate receipt before any possibly committing POST and write a new receipt only after the same TTS identity remains observed.

Tests first: immutable bindings and active-alias independence; consent/hash/UUID/collision refusal; exact POST voice name; restart restoration; complete-plan cache invalidation; failed/ambiguous POST and owner-change receipt exclusion. Root owns the actual metadata binding, one live registration and final integration.

Root usage after cherry-pick into the canonical tree only:

```python
voice_id = '81959ffa-c2ef-4db5-bf95-5df2a24c9404'
profile_dir = manager.PROFILE_ROOT / 'revisions' / '20261017T224025Z-290c3e30ad1b'
expected_hash = 'f35a22ff7e12480c2be2a04180d4bee997aa6e82d809398eb619b58368463f46'
profile = manager.read_profile(profile_dir)
if profile['reference_sha256'] != expected_hash:
    raise ValueError('Expected own-voice reference differs')
# Metadata-only, takes its own activation lock; do not nest this call in it.
binding = manager.bind_native_registration(profile_dir, voice_id)
assert binding['reference_sha256'] == expected_hash
# Separate explicit runtime action, performed by Root only:
with manager.activation_lock(manager.PROFILE_ROOT):
    profile = manager.read_profile(profile_dir)
    if profile['reference_sha256'] != expected_hash:
        raise ValueError('Expected own-voice reference differs')
    timing = manager.native_register(profile, voice_id=voice_id)
```

The explicit UUID call preserves the scc-demo registration itself and active.json. It conservatively removes the old whole-plan startup receipt before POST; it does not manufacture a replacement receipt or claim every planned registration was restored. A later explicit TTS start restores the full alias/UUID plan and writes the PID/create-time-bound receipt only if the observed owner stays the same. Missing manifests remain optional; up to32 explicit UUID mappings are admitted. The helper exposes no arbitrary vendor-voice fallback and no CLI/model/lifecycle change.

Verification with the existing Voice venv (no dependency installation or environment additions):

- voice/voice-profile: `python -B -m unittest discover -p 'test*.py'` —29 tests passed in1.139s.
- voice/native-start: same discovery command —176 tests passed in17.921s. Existing deprecated co_lnotab diagnostic remains; no failure.
- New binding tests were observed failing before the management implementation, and all5 startup regressions were observed failing before startup changes. Existing startup/profile fake contracts were updated for the complete-plan receipt; a pre-existing DesktopSeam fake lacked the RUNTIME attribute required by the current lock guard and now supplies two distinct fictional roots.
- Root independently reviewed the complete two-module diff and approved it without blockers. No actual manifest, registration or runtime receipt was created outside temporary test directories by this task.

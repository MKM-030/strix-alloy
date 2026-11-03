# Voice browser regressions

Run `node --test voice/native-servicenow/tests/browser-parity/regressions.test.cjs`
from the repository root. The tests execute the production Start handler in an
isolated browser fixture, with no network, microphone, instance or model calls.

Coverage includes connected/completed ICE success, promise failures, stale call
callbacks, required media playback, optional analysis failures and ownership of
the audio context. Native auth, deferred-offer signaling and retry policy are
also checked. The retained original reproduces the initial failures with
`VOICE_PARITY_BASELINE=1`; it is a test fixture, not a deployment source.

The production script was saved through its ordinary native form on
`soprasteriaassvsdemo14`, record `b75ca5a73b71fe105237c1c643e45a24`, in the scoped
update set `f8dd4d0e935857185c8132d47aba10c7`. Native form submission stores CRLF;
the canonical source uses LF. Only that known newline conversion differs.
The shared helper and event mapping were independently verified unchanged.

This is a customization of the shared Voice test Start handler. Platform
upgrades may change its original source. Reconcile such changes and rerun these
regressions before reapplying a customization; never overwrite a drifted native
record. The fixtures do not establish real iPhone/Android playback or browser
permission behavior.

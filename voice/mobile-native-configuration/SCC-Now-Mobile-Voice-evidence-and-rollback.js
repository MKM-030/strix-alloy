/*
SCC Now Mobile native Voice button — verified 2026-10-13
Instance: soprasteriaassvsdemo14.service-now.com

Change made: one customer-owned sys_sg_button_instance was inserted.
  sys_id: c9f07f57933f0b54e7f2b9fa6aba101b
  name: SCC Native Voice
  label: Voice
  description: Startet den nativen SCC-Sprachassistenten für die Laptop-Onboarding-Demo.
  parent_table: sys_sg_native_client
  parent: 6fb6c08187403300e0ef0cf888cb0b19 (Now Mobile)
  button: 79e86e8493c68350e7f2b9fa6aba10fe (AI Voice Agent; voice_launcher; Global context)
  location: prominent_action
  icon: 4c0692e6eb20a1104307fd005252287c (MS Icon-Microphone-Unmute)
  order: 10
  active: 1
  disable_offline: 1
  color_theme: primary
  created_by: marcel.kaefke@soprasteria.com
  sys_scope: 469106e153231010df5dddeeff7b12a9 (current application: Recommended Actions for Service)

Before:
  No active prominent action existed for Now Mobile.
  Native instance 8f7da648930a8350e7f2b9fa6aba10b3 used trailing_swipe,
  app-level parent, and no icon or Quick Action mapping.
  Existing SCC Laptop Voice instance 74e2df0393f78354e7f2b9fa6aba1000
  was an active Homepage Quick Action mapped by 78e2df0393f78354e7f2b9fa6aba1003
  to URL function b0e217cf93b78354e7f2b9fa6aba1028 (/scc-demo/).

Fresh secure verification, execution history 1c91371b933f0b54e7f2b9fa6aba10c2:
  PASS exact new instance fields and exactly one active prominent action.
  PASS exactly one active native-function assistant mapping:
    channel 3351561b933f8754e7f2b9fa6aba10c4 -> deployment 8aa131d793f787105c8132d47aba1095.
  PASS deployment name SCC Native Voice, active 1, assistant_type voice.
  PASS Home prominent override channel 8d1eaf5393334b105c8132d47aba10e8:
    sys_sg_navigation_tab b3728c0187403300e0ef0cf888cb0bee -> same assistant.
  PASS original trailing swipe, URL Quick Action, and Homepage mapping unchanged.
  Native launcher has empty condition and condition_script.
  sn_nowassist_va.scc_native_voice.enabled = true; assistant_id matches.
  Marcel has admin and virtual_agent_admin; Now Mobile app config requires no roles.
  Server Now Mobile application 30.1.2 and Mobile App Builder 27.11.0 are active.
  sys_mobile_devices for signed-in Marcel returned no records; installed phone app version unknown.

Creation history: 0df07f57933f0b54e7f2b9fa6aba1019.
Creation used GlideRecordSecure, canCreate, per-field canWrite, exact prerequisite
guards, duplicate-name and active-prominent uniqueness guards, and recorded rollback.
The normal sys_scope field ACL refused an attempted own-record scope correction
before an update; no ACL bypass or scope mutation was performed.
No provider, model, assistant prompt, voice, OOB code, ACL, or original mobile record was changed.

Official references:
  https://www.servicenow.com/docs/r/mobile/config-mobile-ai-voice-agent.html
  https://www.servicenow.com/docs/r/intelligent-experiences/integrate-voice-assistant-with-mobile-app-voice-launcher.html
  https://www.servicenow.com/docs/r/mobile/configuring-prominent-action-button.html
  https://www.servicenow.com/docs/r/mobile/metadata-refresh.html

Phone acceptance still required:
  In Now Mobile, select this instance, open Home, scroll to the top, pull down
  until the refresh icon appears and release. Tap Voice / microphone, allow
  microphone if prompted, and verify the German native SCC assistant starts.
  If the installed client is old, update Now Mobile through its official store.
  No specific minimum native app version was established from official docs.

ROLLBACK ONLY: Running the IIFE below in normal Global Background Scripts
deactivates only the exact new customer-owned instance. It preserves the record
for audit/recovery and leaves the prior native swipe and web shortcut intact.
It refuses to proceed if identity, creator, mapping, scope, or normal ACL changed.
This rollback has NOT been run. Its JavaScript syntax was checked locally.
*/
(function () {
    var id = 'c9f07f57933f0b54e7f2b9fa6aba101b';
    var record = new GlideRecordSecure('sys_sg_button_instance');
    if (!record.get(id) || !record.canRead()) {
        throw 'Rollback refused: target is missing or unreadable';
    }
    var expected = {
        name: 'SCC Native Voice',
        label: 'Voice',
        sys_created_by: 'marcel.kaefke@soprasteria.com',
        sys_scope: '469106e153231010df5dddeeff7b12a9',
        parent_table: 'sys_sg_native_client',
        parent: '6fb6c08187403300e0ef0cf888cb0b19',
        button: '79e86e8493c68350e7f2b9fa6aba10fe',
        location: 'prominent_action',
        icon: '4c0692e6eb20a1104307fd005252287c'
    };
    for (var field in expected) {
        if (!record.isValidField(field) || !record.getElement(field).canRead() ||
            String(record.getValue(field)) !== expected[field]) {
            throw 'Rollback refused: guard mismatch on ' + field;
        }
    }
    if (!record.getElement('active').canRead()) {
        throw 'Rollback refused: active field unreadable';
    }
    if (record.getValue('active') === '0') {
        gs.print('Rollback already applied: ' + id + ' is inactive');
        return;
    }
    if (record.getValue('active') !== '1' || !record.canWrite() ||
        !record.getElement('active').canWrite()) {
        throw 'Rollback refused: normal record or active-field ACL denied';
    }
    record.setValue('active', false);
    if (!record.update()) {
        throw 'Rollback failed: normal update did not return an ID';
    }
    var readback = new GlideRecordSecure('sys_sg_button_instance');
    if (!readback.get(id) || !readback.canRead() ||
        !readback.getElement('active').canRead() || readback.getValue('active') !== '0') {
        throw 'Rollback readback failed';
    }
    gs.print('Rollback verified: only new SCC Native Voice instance ' + id + ' is inactive');
})();

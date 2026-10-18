// Authorized bounded SCC Local Voice static message translation.
// Execute once via ordinary Scripts - Background, Global; normal workflow and ACLs.
// No provider, credential, role, current application or current update-set change.
(function () {
  var TABLE = 'sys_cs_context_profile_message';
  var PROFILE = 'c623e20f93374354e7f2b9fa6aba1081';
  var SCOPE = '7cc4ec81533121106b38ddeeff7b12ee';
  var specs = [
  {
    "sys_id": "1e23260f93374354e7f2b9fa6aba102d",
    "type": "Show me everything",
    "before": "View all options",
    "after": "Alle M\u00f6glichkeiten anzeigen"
  },
  {
    "sys_id": "2223260f93374354e7f2b9fa6aba1051",
    "type": "Record Producer Fallback",
    "before": "OK, I'll go ahead and create a ticket for you.",
    "after": "Ich erstelle jetzt ein Ticket f\u00fcr Sie."
  },
  {
    "sys_id": "2623260f93374354e7f2b9fa6aba1074",
    "type": "AI record producer button",
    "before": "Create a generic ticket",
    "after": "Allgemeines Ticket erstellen"
  },
  {
    "sys_id": "2a23260f93374354e7f2b9fa6aba10a8",
    "type": "Skill selection",
    "before": "Ask me a question to get started or see a list of everything I can help with.",
    "after": "Stellen Sie mir eine Frage oder sehen Sie sich an, wobei ich Ihnen helfen kann."
  },
  {
    "sys_id": "5223260f93374354e7f2b9fa6aba1020",
    "type": "Live agent",
    "before": "Unfortunately, I don't have an answer for that right now. Let me connect you to an agent. One moment.",
    "after": "Darauf habe ich gerade keine Antwort. Ich verbinde Sie mit einem Servicemitarbeiter. Einen Moment bitte."
  },
  {
    "sys_id": "6e23260f93374354e7f2b9fa6aba1078",
    "type": "Live agent button",
    "before": "Request a live chat",
    "after": "Live-Chat anfordern"
  },
  {
    "sys_id": "6e23260f93374354e7f2b9fa6aba1089",
    "type": "Document QnA End",
    "before": "Document QnA has ended",
    "after": "Die Dokumentenfrage wurde abgeschlossen."
  },
  {
    "sys_id": "9223260f93374354e7f2b9fa6aba1000",
    "type": "Self Service Fallback",
    "before": "I can't find anything on that directly but I can help you explore other options.",
    "after": "Dazu habe ich keine passende Antwort gefunden. Ich kann Ihnen bei anderen M\u00f6glichkeiten helfen."
  },
  {
    "sys_id": "9623260f93374354e7f2b9fa6aba1012",
    "type": "End chat button",
    "before": "End this chat",
    "after": "Dieses Gespr\u00e4ch beenden"
  }
];
  var report = {operation:'SCC_GERMAN_STATIC_MESSAGES_REMAINDER_20261013',writes:0,preflight:[],readbacks:[],updateSetLookup:[],status:'preflight'};
  function fail(reason) { report.status='aborted'; report.reason=reason; gs.print('[SCC GERMAN STATIC] '+JSON.stringify(report)); }
  function placeholders(text) { return (String(text).match(/\{\d+\}/g) || []).sort().join(','); }
  function read(spec) {
    var gr=new GlideRecordSecure(TABLE);
    if (!gr.get(spec.sys_id) || !gr.canRead() || !gr.canWrite()) throw new Error('record_access_'+spec.sys_id);
    var fields=['message','context_profile','type','sys_scope','sys_mod_count','sys_updated_on'];
    for(var j=0;j<fields.length;j++) if(!gr.isValidField(fields[j]) || !gr.getElement(fields[j]).canRead()) throw new Error('field_access_'+spec.sys_id+'_'+fields[j]);
    if(!gr.getElement('message').canWrite()) throw new Error('message_write_denied_'+spec.sys_id);
    if(String(gr.getValue('context_profile'))!==PROFILE || String(gr.getValue('sys_scope'))!==SCOPE || String(gr.getDisplayValue('type'))!==spec.type) throw new Error('record_identity_'+spec.sys_id);
    return gr;
  }
  try {
    var dst=new GlideRecordSecure('sys_update_set');
    dst.addQuery('name','SCC Voice Deutsch 2026-10-13');
    dst.addQuery('application',SCOPE);
    dst.setLimit(3); dst.query();
    while(dst.next()) report.updateSetLookup.push({sys_id:String(dst.getUniqueValue()),name:String(dst.getValue('name')),application:String(dst.getValue('application')),state:String(dst.getValue('state'))});
    var snapshots=[];
    for(var i=0;i<specs.length;i++) {
      var spec=specs[i];
      if(placeholders(spec.before)!==placeholders(spec.after)) throw new Error('placeholder_guard_'+spec.sys_id);
      var gr=read(spec);
      if(String(gr.getValue('message'))!==spec.before) throw new Error('before_value_'+spec.sys_id);
      var snapshot={sys_id:spec.sys_id,type:spec.type,before:spec.before,after:spec.after,mod_count:String(gr.getValue('sys_mod_count')),updated_on:String(gr.getValue('sys_updated_on'))};
      snapshots.push(snapshot); report.preflight.push(snapshot);
    }
    // All target records pass before the first mutation. Each record is re-read again immediately before its own normal update.
    for(var k=0;k<specs.length;k++) {
      var item=specs[k], before=snapshots[k], target=read(item);
      if(String(target.getValue('message'))!==item.before || String(target.getValue('sys_mod_count'))!==before.mod_count || String(target.getValue('sys_updated_on'))!==before.updated_on) throw new Error('concurrent_change_'+item.sys_id);
      target.setValue('message',item.after);
      var saved=target.update();
      if(!saved || String(saved)!==item.sys_id) throw new Error('update_failed_'+item.sys_id);
      report.writes++;
      var verify=read(item);
      if(String(verify.getValue('message'))!==item.after) throw new Error('readback_mismatch_'+item.sys_id);
      report.readbacks.push({sys_id:item.sys_id,type:item.type,message:String(verify.getValue('message')),context_profile:String(verify.getValue('context_profile')),sys_scope:String(verify.getValue('sys_scope')),mod_count:String(verify.getValue('sys_mod_count')),updated_on:String(verify.getValue('sys_updated_on'))});
    }
    report.status='verified';
    gs.print('[SCC GERMAN STATIC] '+JSON.stringify(report));
  } catch (e) { fail(String(e.message || 'platform_error')); }
})();

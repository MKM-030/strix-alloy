// Root-authorized SCC voice governance, ordinary ACL and workflow checks.
// No current application or current update-set setter; no provider records.
(function () {
  var name='SCC Voice Deutsch 2026-10-13';
  var scope='7cc4ec81533121106b38ddeeff7b12ee';
  var report={operation:'SCC_GERMAN_UPDATE_SET_CREATE_20261013',inserts:0,status:'preflight'};
  function verify(id) {
    var gr=new GlideRecordSecure('sys_update_set');
    if(!gr.get(id) || !gr.canRead()) throw new Error('readback_access');
    var fields=['name','application','state'];
    for(var i=0;i<fields.length;i++) if(!gr.isValidField(fields[i]) || !gr.getElement(fields[i]).canRead()) throw new Error('readback_field_access');
    if(String(gr.getValue('name'))!==name || String(gr.getValue('application'))!==scope || String(gr.getValue('state'))!=='in_progress') throw new Error('readback_identity');
    return {sys_id:String(gr.getUniqueValue()),name:String(gr.getValue('name')),application:String(gr.getValue('application')),state:String(gr.getValue('state'))};
  }
  try {
    var existing=new GlideRecordSecure('sys_update_set');
    existing.addQuery('name',name); existing.addQuery('application',scope); existing.setLimit(2); existing.query();
    if(existing.next()) {
      var id=String(existing.getUniqueValue());
      if(existing.next()) throw new Error('multiple_existing_sets');
      report.record=verify(id); report.status='existing_verified';
    } else {
      var set=new GlideRecordSecure('sys_update_set'); set.initialize();
      if(!set.canCreate()) throw new Error('create_denied');
      var writable=['name','application','state'];
      for(var j=0;j<writable.length;j++) if(!set.isValidField(writable[j]) || !set.getElement(writable[j]).canWrite()) throw new Error('create_field_denied_'+writable[j]);
      set.setValue('name',name); set.setValue('application',scope); set.setValue('state','in_progress');
      var created=set.insert();
      if(!created) throw new Error('insert_failed');
      report.inserts=1; report.record=verify(String(created)); report.status='created_verified';
    }
  } catch(e) { report.status='aborted'; report.reason=String(e.message || 'platform_error'); }
  gs.print('[SCC GERMAN SET] '+JSON.stringify(report));
})();

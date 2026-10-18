// READ ONLY: exact own translated messages and their customer update identities.
(function () {
 var TABLE='sys_cs_context_profile_message', PROFILE='c623e20f93374354e7f2b9fa6aba1081', SCOPE='7cc4ec81533121106b38ddeeff7b12ee';
 var specs=[
  {
    "sys_id": "9e23260f93374354e7f2b9fa6aba1047",
    "type": "QNA LLM Request",
    "after": "Die Antwort wird erstellt."
  },
  {
    "sys_id": "a223260f93374354e7f2b9fa6aba106b",
    "type": "Record producer button",
    "after": "Allgemeines Ticket erstellen"
  },
  {
    "sys_id": "a623260f93374354e7f2b9fa6aba108e",
    "type": "Document QnA Start",
    "after": "Die Dokumentenfrage wird bearbeitet."
  },
  {
    "sys_id": "a623260f93374354e7f2b9fa6aba109f",
    "type": "Now Assist Thinking Start",
    "after": "Ihre Anfrage wird bearbeitet."
  },
  {
    "sys_id": "aa23260f93374354e7f2b9fa6aba10b1",
    "type": "AI web search button",
    "after": "Im Internet suchen"
  },
  {
    "sys_id": "d223260f93374354e7f2b9fa6aba1029",
    "type": "Guardian generic message",
    "after": "Now Assist hat Inhalte erkannt, die m\u00f6glicherweise sch\u00e4dlich, sensibel oder anst\u00f6\u00dfig sind. Bitte formulieren Sie Ihre Anfrage anders oder fragen Sie nach etwas anderem."
  },
  {
    "sys_id": "d623e20f93374354e7f2b9fa6aba10f2",
    "type": "AI live agent button",
    "after": "Live-Chat anfordern"
  },
  {
    "sys_id": "da23260f93374354e7f2b9fa6aba1004",
    "type": "Fallback",
    "after": "Dazu habe ich keine passende Antwort gefunden. Ich kann Ihnen bei anderen M\u00f6glichkeiten helfen."
  },
  {
    "sys_id": "de23260f93374354e7f2b9fa6aba1016",
    "type": "Now Assist Execution End",
    "after": "\u201e{0}\u201c wird abgeschlossen."
  },
  {
    "sys_id": "e623260f93374354e7f2b9fa6aba104c",
    "type": "Now Assist Execution Start",
    "after": "\u201e{0}\u201c wird ausgef\u00fchrt."
  },
  {
    "sys_id": "ea23260f93374354e7f2b9fa6aba106f",
    "type": "Web search button",
    "after": "Im Internet suchen"
  },
  {
    "sys_id": "ee23260f93374354e7f2b9fa6aba10a3",
    "type": "Retrieve Search Results",
    "after": "Die ben\u00f6tigten Informationen werden gesucht."
  },
  {
    "sys_id": "2223260f93374354e7f2b9fa6aba1062",
    "type": "AI Agent Planning",
    "after": "Die Assistenten bearbeiten Ihre Anfrage."
  },
  {
    "sys_id": "5623260f93374354e7f2b9fa6aba1043",
    "type": "Router LLM Request",
    "after": "Ihre Anfrage wird gepr\u00fcft."
  },
  {
    "sys_id": "5e23260f93374354e7f2b9fa6aba100d",
    "type": "Skill Start",
    "after": "\u201e{0}\u201c wird gestartet."
  },
  {
    "sys_id": "6a23260f93374354e7f2b9fa6aba1066",
    "type": "Rerank Documents",
    "after": "Die Details werden gepr\u00fcft."
  },
  {
    "sys_id": "1e23260f93374354e7f2b9fa6aba102d",
    "type": "Show me everything",
    "after": "Alle M\u00f6glichkeiten anzeigen"
  },
  {
    "sys_id": "2223260f93374354e7f2b9fa6aba1051",
    "type": "Record Producer Fallback",
    "after": "Ich erstelle jetzt ein Ticket f\u00fcr Sie."
  },
  {
    "sys_id": "2623260f93374354e7f2b9fa6aba1074",
    "type": "AI record producer button",
    "after": "Allgemeines Ticket erstellen"
  },
  {
    "sys_id": "2a23260f93374354e7f2b9fa6aba10a8",
    "type": "Skill selection",
    "after": "Stellen Sie mir eine Frage oder sehen Sie sich an, wobei ich Ihnen helfen kann."
  },
  {
    "sys_id": "5223260f93374354e7f2b9fa6aba1020",
    "type": "Live agent",
    "after": "Darauf habe ich gerade keine Antwort. Ich verbinde Sie mit einem Servicemitarbeiter. Einen Moment bitte."
  },
  {
    "sys_id": "6e23260f93374354e7f2b9fa6aba1078",
    "type": "Live agent button",
    "after": "Live-Chat anfordern"
  },
  {
    "sys_id": "6e23260f93374354e7f2b9fa6aba1089",
    "type": "Document QnA End",
    "after": "Die Dokumentenfrage wurde abgeschlossen."
  },
  {
    "sys_id": "9223260f93374354e7f2b9fa6aba1000",
    "type": "Self Service Fallback",
    "after": "Dazu habe ich keine passende Antwort gefunden. Ich kann Ihnen bei anderen M\u00f6glichkeiten helfen."
  },
  {
    "sys_id": "9623260f93374354e7f2b9fa6aba1012",
    "type": "End chat button",
    "after": "Dieses Gespr\u00e4ch beenden"
  }
];
 var report={operation:'SCC_GERMAN_MESSAGE_AUDIT_20261013',writes:0,sets:[],records:[],status:'reading'};
 function field(gr,name) { if(!gr.isValidField(name) || !gr.getElement(name).canRead()) throw new Error('field_read_denied_'+name); return String(gr.getValue(name)||''); }
 try {
   var set=new GlideRecordSecure('sys_update_set'); set.addQuery('name','STARTSWITH','SCC'); set.addQuery('application',SCOPE); set.addQuery('state','in_progress'); set.setLimit(10); set.query();
   while(set.next()) report.sets.push({sys_id:String(set.getUniqueValue()),name:field(set,'name'),application:field(set,'application'),state:field(set,'state')});
   for(var i=0;i<specs.length;i++) {
     var item=specs[i], live=new GlideRecordSecure(TABLE);
     if(!live.get(item.sys_id) || !live.canRead()) throw new Error('live_access_'+item.sys_id);
     if(field(live,'context_profile')!==PROFILE || field(live,'sys_scope')!==SCOPE || field(live,'message')!==item.after || String(live.getDisplayValue('type'))!==item.type) throw new Error('live_identity_'+item.sys_id);
     var row={sys_id:item.sys_id,type:item.type,message:item.after,current_verified:true,mod_count:field(live,'sys_mod_count'),updated_on:field(live,'sys_updated_on'),customer_updates:[],nonmatching_captures:0};
     var upd=new GlideRecordSecure('sys_update_xml'); upd.addQuery('name',TABLE+'_'+item.sys_id); upd.setLimit(4); upd.query();
     while(upd.next()) {
       var text=field(upd,'payload'); if(text.length>12000) throw new Error('payload_size_'+item.sys_id);
       var xml=new XMLDocument2(); xml.parseXML(text); var base='/record_update/'+TABLE+'/';
       var root=xml.getNode('/record_update');
       var matches=root && String(root.getAttribute('table'))===TABLE && String(xml.getNodeText(base+'sys_id'))===item.sys_id && String(xml.getNodeText(base+'context_profile'))===PROFILE && String(xml.getNodeText(base+'sys_scope'))===SCOPE && String(xml.getNodeText(base+'message'))===item.after;
       if(matches) row.customer_updates.push({sys_id:String(upd.getUniqueValue()),name:field(upd,'name'),update_set:field(upd,'update_set'),update_set_display:String(upd.getDisplayValue('update_set')),payload_identity_verified:true,mod_count:field(upd,'sys_mod_count'),updated_on:field(upd,'sys_updated_on')});
       else row.nonmatching_captures++;
     }
     row.unique_matching_capture=row.customer_updates.length===1; report.records.push(row);
   }
   report.status='verified';
 } catch(e) { report.status='aborted'; report.reason=String(e.message||'platform_error'); }
 gs.print('[SCC GERMAN AUDIT] '+JSON.stringify(report));
})();

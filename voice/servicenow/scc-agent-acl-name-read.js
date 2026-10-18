/* Read only; find SCC ACL names without assuming an ACL type. */
(function(){
var out={writes:0,acl:[],roles:[],type_choices:[],type_dictionary:[]},ids=[];
var q=new GlideRecord('sys_security_acl');
var term=q.addQuery('name','CONTAINS','SCC Laptop Onboarding');term.addOrCondition('name','CONTAINS','HR case creator SCC Local Voice');
q.setLimit(21);q.query();if(q.getRowCount()>20)throw new Error('ACL read limit');
while(q.next()){ids.push(String(q.getUniqueValue()));var a=row(q,['name','type','operation','active','admin_overrides','condition']);a.type_display=q.getDisplayValue('type');a.script_length=String(q.getValue('script')||'').length;out.acl.push(a);}
if(ids.length){var r=new GlideRecord('sys_security_acl_role');r.addQuery('sys_security_acl','IN',ids.join(','));r.setLimit(51);r.query();if(r.getRowCount()>50)throw new Error('Role read limit');while(r.next()){var rr=row(r,['sys_security_acl','sys_user_role']);rr.role_name=r.getDisplayValue('sys_user_role');out.roles.push(rr);}}
var d=new GlideRecord('sys_dictionary');d.addQuery('name','sys_security_acl');d.addQuery('element','type');d.query();while(d.next())out.type_dictionary.push(row(d,['element','internal_type','reference','choice']));
var c=new GlideRecord('sys_choice');c.addQuery('name','sys_security_acl');c.addQuery('element','type');c.addQuery('language','en');c.setLimit(101);c.query();if(c.getRowCount()>100)throw new Error('Type choice read limit');while(c.next())out.type_choices.push({value:String(c.getValue('value')),label:String(c.getValue('label')),inactive:String(c.getValue('inactive'))});
gs.info('[SCC ACL Name Read] '+JSON.stringify(out));
function row(gr,fields){var x={table:String(gr.getRecordClassName()),sys_id:String(gr.getUniqueValue())};fields=fields.concat(['sys_scope','sys_created_on','sys_created_by','sys_updated_on','sys_mod_count']);for(var i=0;i<fields.length;i++)if(gr.isValidField(fields[i]))x[fields[i]]=String(gr.getValue(fields[i])||'');return x;}
})();

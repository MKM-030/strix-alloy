"""Reproducible OFFLINE Global update set; never contacts or deploys to ServiceNow."""
import hashlib
import json
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
NAMESPACE = uuid.UUID('e980bd5b-cc90-4b5c-b139-054df28d0bb1')


def identity(name):
    return uuid.uuid5(NAMESPACE, name).hex


def build():
    records = []

    def record(table, identity_name, **fields):
        fields = {'sys_id': identity(table + ':' + identity_name), 'sys_scope': 'global',
                  'sys_package': 'global', **fields}
        records.append((table, fields))
        return fields['sys_id']

    tables = {
        'u_scc_voice_task': {'u_command_key': True},
        'u_scc_voice_transition': {'u_command_key': True, 'u_predecessor_slot': True},
        'u_scc_voice_operation': {'u_operation_key': True},
        'u_scc_voice_dispatch_claim': {'u_operation_key': True},
        'u_scc_voice_event': {'u_source_event_key': True, 'u_task_sequence': True},
    }
    manifest = {'package_revision': 'responsive-tasks-v2-candidate-1', 'scope': 'global',
                'deployment': 'not_applied', 'safe_write': False, 'tables': {}, 'scripts': {},
                'native_projection': {'file': 'native-registry-v2.candidate.js', 'scope': 'sn_voice_aia',
                    'scope_id': '022bd6e9b720a61081fee3fdde11a9df', 'imported': False,
                    'missing': 'separate REST definition and authentication/accessibility metadata readback'},
                'legacy_source_sha256': '79f7a17ccc0887ade5004cf10bb12df4a78012ba583590474f84f6cb443f7ffe'}
    for table, unique_fields in tables.items():
        record('sys_db_object', table, name=table, label=table, is_extendable='false',
               access='package_private', create_access='false', read_access='false',
               update_access='false', delete_access='false')
        record('sys_dictionary', table, name=table, element='', internal_type='collection')
        fields = {'u_key': {'unique': True, 'mandatory': True, 'length': 128},
                  'u_data': {'mandatory': True, 'length': 16000},
                  'u_owner': {'reference': 'sys_user'},
                  **{key: {'unique': unique, 'mandatory': True, 'length': 260} for key, unique in unique_fields.items()}}
        if table != 'u_scc_voice_task':
            fields['u_task'] = {'reference': 'u_scc_voice_task', 'mandatory': True}
            fields['u_task_key'] = {'mandatory': True, 'length': 128}
        if table in ('u_scc_voice_task', 'u_scc_voice_transition', 'u_scc_voice_operation'):
            for field in ('u_service', 'u_agent', 'u_tool', 'u_registry_revision'):
                fields[field] = {'mandatory': True, 'length': 128}
        if table in ('u_scc_voice_transition', 'u_scc_voice_operation'):
            for field in ('u_payload_hash', 'u_proposal_key', 'u_confirmation_key'):
                fields[field] = {'length': 128}
        if table == 'u_scc_voice_dispatch_claim':
            fields['u_operation'] = {'reference': 'u_scc_voice_operation', 'mandatory': True}
        for field, options in fields.items():
            props = dict(name=table, element=field, column_label=field,
                         internal_type='reference' if options.get('reference') else 'string',
                         mandatory=str(options.get('mandatory', False)).lower(),
                         unique=str(options.get('unique', False)).lower(), max_length=str(options.get('length', 32)))
            if options.get('reference'):
                props['reference'] = options['reference']
            record('sys_dictionary', table + '.' + field, **props)
        manifest['tables'][table] = fields
        # ACLs are restrictive metadata only: no role records or grants.
        for operation in ('create', 'read', 'write', 'delete'):
            for suffix in ('', '.*'):
                record('sys_security_acl', table + suffix + ':' + operation, name=table + suffix,
                       type='record', operation=operation, active='true', admin_overrides='false',
                       advanced='true', script='answer = false;', description='Owned authority: use authenticated narrow resources only.')
        record('sys_script', table + ':immutable', name='SCC voice immutable ' + table,
               collection=table, active='true', when='before', order='1', action_insert='false',
               action_update='true', action_delete='true', action_query='false',
               script='(function executeRule(current, previous) { current.setAbortAction(true); })(current, previous);')
    includes = ['LocalLLMVoiceTaskControl', 'LocalLLMVoiceOrderGuard', 'LocalLLMVoiceRepository',
                'LocalLLMVoicePlatform', 'LocalLLMVoiceResource', 'LocalLLMSCCOrderBusiness']
    for name in includes:
        raw = (ROOT / (name + '.js')).read_bytes()
        manifest['scripts'][name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'active_on_import': False}
        record('sys_script_include', name, name=name, api_name='global.' + name, active='false',
               client_callable='false', access='package_private', script=raw.decode('utf-8'),
               description='Inactive prospective authority package; qualification required before any activation.')
    api = record('sys_ws_definition', 'scc_voice_tasks', name='SCC Voice Tasks candidate',
                 service_id='scc_voice_tasks', active='false', enforce_acl='true',
                 requires_authentication='true', requires_acl_authorization='true')
    version = record('sys_ws_version', 'scc_voice_tasks:v2', web_service_definition=api,
                     version='v2', is_default='true')
    manifest['routes'] = []
    for kind, method, route in [('registry', 'GET', '/registry'), ('create', 'POST', '/tasks'),
                                 ('status', 'GET', '/tasks/{id}'), ('command', 'POST', '/tasks/{id}/commands'),
                                 ('operation', 'GET', '/operations/{id}')]:
        record('sys_ws_operation', kind, name='SCC voice ' + kind, web_service_definition=api,
               web_service_version=version, http_method=method, relative_path=route, active='false',
               requires_authentication='true', requires_acl_authorization='true',
               operation_script="(function process(request,response) { new LocalLLMVoiceResource().run('" + kind + "',request,response); })(request,response);")
        manifest['routes'].append({'method': method, 'path': '/api/global/scc_voice_tasks/v2' + route, 'active_on_import': False})
    # Do not import guessed native sn_aia_tool metadata or edit existing binding IDs.
    manifest['prepare_tool'] = {'file': 'prepare-only-tool.js', 'imported': False,
                                'reason': 'native tool metadata and guarded agent binding require separately reviewed migration'}
    manifest['record_count'] = len(records)
    root = ET.Element('unload', unload_date='2026-10-23 00:00:00')
    remote_id = identity('remote_update_set')
    remote = ET.SubElement(root, 'sys_remote_update_set', action='INSERT_OR_UPDATE')
    for key, value in {'sys_id': remote_id, 'name': 'SCC Responsive Tasks v2 INACTIVE CANDIDATE',
                       'state': 'loaded', 'application': 'global',
                       'description': 'Offline prepared metadata. No live qualification; includes and REST routes inactive.'}.items():
        ET.SubElement(remote, key).text = value
    for table, fields in records:
        payload = ET.Element('record_update', table=table)
        item = ET.SubElement(payload, table, action='INSERT_OR_UPDATE')
        for key, value in fields.items():
            ET.SubElement(item, key).text = str(value)
        customer = ET.SubElement(root, 'sys_update_xml', action='INSERT_OR_UPDATE')
        for key, value in {'sys_id': identity('update:' + fields['sys_id']), 'remote_update_set': remote_id,
                           'name': table + '_' + fields['sys_id'], 'action': 'INSERT_OR_UPDATE',
                           'application': 'global', 'payload': ET.tostring(payload, encoding='unicode')}.items():
            ET.SubElement(customer, key).text = value
    ET.indent(root)
    ET.ElementTree(root).write(ROOT / 'responsive-tasks.inactive.update-set.xml', encoding='utf-8', xml_declaration=True)
    (ROOT / 'schema-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    build()

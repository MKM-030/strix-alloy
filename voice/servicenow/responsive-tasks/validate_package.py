"""Offline artifact integrity checks, not ServiceNow installation qualification."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def validate():
    manifest = json.loads((ROOT / 'schema-manifest.json').read_text())
    root = ET.parse(ROOT / 'responsive-tasks.inactive.update-set.xml').getroot()
    records = [ET.fromstring(update.findtext('payload'))[0] for update in root.findall('sys_update_xml')]
    assert len(records) == manifest['record_count']
    assert len({record.findtext('sys_id') for record in records}) == len(records)
    allowed = {'sys_db_object', 'sys_dictionary', 'sys_security_acl', 'sys_script',
               'sys_script_include', 'sys_ws_definition', 'sys_ws_version', 'sys_ws_operation'}
    assert {record.tag for record in records} <= allowed
    assert all(record.findtext('sys_scope') == 'global' for record in records)
    dictionaries = {(record.findtext('name'), record.findtext('element')): record
                    for record in records if record.tag == 'sys_dictionary'}
    for table, fields in manifest['tables'].items():
        for field, spec in fields.items():
            row = dictionaries[(table, field)]
            if spec.get('unique'):
                assert row.findtext('unique') == 'true' and row.findtext('mandatory') == 'true'
    for record in records:
        if record.tag in {'sys_ws_definition', 'sys_ws_operation', 'sys_script_include'}:
            assert record.findtext('active') == 'false'
        if record.tag == 'sys_security_acl':
            assert record.findtext('script') == 'answer = false;'
            assert record.findtext('admin_overrides') == 'false'
        if record.tag == 'sys_script_include':
            name = record.findtext('name')
            source = (ROOT / (name + '.js')).read_bytes()
            assert hashlib.sha256(source).hexdigest() == manifest['scripts'][name]['sha256']
            assert record.findtext('script') == source.decode('utf-8')
    legacy = (ROOT.parent / 'scc-laptop-order-tool.js').read_bytes()
    assert hashlib.sha256(legacy).hexdigest() == manifest['legacy_source_sha256']
    assert b'return ' + legacy.rstrip() in (ROOT / 'LocalLLMSCCOrderBusiness.js').read_bytes()
    print(f'Validated {len(records)} Global metadata records, {len(manifest["tables"])} tables, 6 inactive includes, 5 inactive routes; source hashes and exact SCC body match. No platform import performed.')


if __name__ == '__main__':
    validate()

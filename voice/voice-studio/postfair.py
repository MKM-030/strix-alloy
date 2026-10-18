"""Read-only seal for the completed SCC campaign; never mutates recordings/services."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat

DUE = datetime(2026, 10, 16, 6, tzinfo=timezone.utc)
DUE_TEXT = '2026-10-16T06:00:00Z'
HELPER_SHA256 = '06a34af5d3cebddb4458bfe91a2f5720f39588e05f848a621a5a09d7592767c1'
RETENTION_NOTICE = 'Neue Aufnahmen bleiben gespeichert, bis Sie oder ein Administrator sie löschen.'

def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None: raise ValueError('Timezone required')
    return result

def read_plain(path):
    path = Path(path)
    for current in [path, *path.parents]:
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse path')
    if not path.is_file() or path.stat().st_size > 8192: raise ValueError('Invalid seal file')
    return path.read_bytes()

def completed_campaign(runtime, helper_path=None):
    """Accept only a private local completion seal tied to the fixed cleanup result."""
    try:
        runtime = Path(runtime)
        marker = json.loads(read_plain(runtime / 'fair-campaign-completed.json'))
        receipt_bytes = read_plain(runtime / 'fair-campaign-cleanup-result.json')
        receipt = json.loads(receipt_bytes)
        expected = {'remaining_fair_profiles':0,'selected_profile_id':'synthetic-scc-demo','native_sessions':0}
        if (marker.get('schema_version') != 1 or marker.get('campaign') != 'scc-2026'
                or marker.get('due_at_utc') != DUE_TEXT or marker.get('postfair_enabled') is not True
                or marker.get('verified') != expected or marker.get('cleanup_helper_sha256') != HELPER_SHA256
                or marker.get('cleanup_result_sha256') != hashlib.sha256(receipt_bytes).hexdigest()
                or receipt.get('status') != 'purged' or receipt.get('schema_version') != 1
                or receipt.get('due_at_utc') != DUE_TEXT
                or timestamp(receipt['attempted_at_utc']) < DUE
                or timestamp(marker['completed_at_utc']) < timestamp(receipt['attempted_at_utc'])):
            return False
        helper_path = Path(helper_path or Path(__file__).with_name('retention_cleanup.py'))
        return hashlib.sha256(helper_path.read_bytes()).hexdigest() == HELPER_SHA256
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False

def fresh_consent(consent, now):
    try:
        return (consent.get('own_voice') is True
            and consent.get('scope') == 'local_synthetic_voice_and_servicenow_demo'
            and consent.get('retention') == 'until_deleted'
            and consent.get('retention_notice') == RETENTION_NOTICE
            and DUE < timestamp(consent['confirmed_at_utc']) <= now)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False

def fresh_profile(profile, now):
    try:
        return (profile.get('kind') == 'authorized_own_voice'
            and DUE < timestamp(profile['created_at_utc']) <= now
            and fresh_consent(profile.get('consent'), now))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False

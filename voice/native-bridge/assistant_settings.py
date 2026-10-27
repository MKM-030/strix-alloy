"""Validated, request-local native assistant projection (no network or credentials).

Native cloud voice identifiers and neural-VAD amplitudes remain metadata. They
never select a local speech model or replace the host's PCM energy threshold.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
import re
import unicodedata

_SYS_ID = re.compile(r'[0-9a-f]{32}\Z')
_LANGUAGE = re.compile(
    r'(?:(?:[A-Za-z]{2,3}(?:-[A-Za-z]{3}){0,3}|[A-Za-z]{4}|[A-Za-z]{5,8})'
    r'(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?'
    r'(?:-(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*'
    r'(?:-[0-9A-WY-Za-wy-z](?:-[A-Za-z0-9]{2,8})+)*'
    r'(?:-x(?:-[A-Za-z0-9]{1,8})+)?|x(?:-[A-Za-z0-9]{1,8})+)\Z')
_GRANDFATHERED = frozenset(('art-lojban', 'cel-gaulish', 'en-gb-oed', 'i-ami', 'i-bnn',
    'i-default', 'i-enochian', 'i-hak', 'i-klingon', 'i-lux', 'i-mingo', 'i-navajo',
    'i-pwn', 'i-tao', 'i-tay', 'i-tsu', 'no-bok', 'no-nyn', 'sgn-be-fr', 'sgn-be-nl',
    'sgn-ch-de', 'zh-guoyu', 'zh-hakka', 'zh-min', 'zh-min-nan', 'zh-xiang'))
_BEHAVIOR_FIELDS = frozenset({
    'language', 'voice_profile', 'tts_config_sys_id', 'enable_language_selection',
    'enable_dtmf', 'language_input_selection', 'max_call_duration_in_minutes',
    'user_inactivity_threshold_in_seconds', 'filler_message_delay_in_seconds',
    'noise_suppression_level', 'persist_context_data', 'orchestration_mode',
    'gateway_mode', 'number_delivery', 'identifier_delivery', 'retry_prefix',
    'goodbye_message', 'voice_max_retries', 'start_time_in_ms', 'stop_time_in_ms',
    'communication_channel', 'caller_identification_fields', 'capture_pre_transfer_details',
    'enable_phone_number_based_identification', 'enable_multifactor_authentication',
    'auto_authenticate', 'disable_auth_v2', 'primary_authentication_type',
    'secondary_authentication_type', 'step_up_authentication_type',
    'primary_identification_type', 'secondary_identification_type',
    'require_auth_for_fallback_record_creation', 'fallback_option',
    'create_ticket_fallback_record_producer_sys_id', 'mobile_fallback_record_producer',
    'push_notification_max_polling_retries', 'voice_minutes_account_is_locked',
    'sip_context_header',
})
_NOTICE_CODES = frozenset(('INPUT_LOST', 'BUSY_AUDIO', 'BUSY_TEXT', 'ASR_EMPTY',
                           'ASR_FAILED', 'TURN_FAILED', 'LANGUAGE_RETRY', 'USER_INACTIVITY'))
# Owned local notices. Other languages require an explicit configured translation.
_NOTICE_MESSAGES = {
    "de": {
        "INPUT_LOST": "Die Mikrofonverbindung wurde unterbrochen. Weitere Antworten werden nicht weitergeleitet. Dieser Anruf wird beendet, sobald die laufende Anfrage abgeschlossen ist.",
        "BUSY_AUDIO": "Die letzte Aufnahme konnte nicht angenommen werden. Bitte warten Sie auf den Abschluss der aktuellen Anfrage.",
        "BUSY_TEXT": "Ihre letzte Antwort wurde erkannt, aber nicht weitergeleitet. Bitte warten Sie auf den Abschluss der aktuellen Anfrage.",
        "ASR_EMPTY": "Ich konnte keine Sprache erkennen. Bitte wiederholen Sie Ihre Antwort.",
        "ASR_FAILED": "Die Spracherkennung ist fehlgeschlagen. Bitte wiederholen Sie Ihre Antwort.",
        "TURN_FAILED": "Der Sprachdialog konnte nicht fortgesetzt werden. Weitere Antworten werden nicht weitergeleitet. Bitte beenden Sie diesen Anruf.",
        "LANGUAGE_RETRY": "Bitte wählen Sie eine Sprache.",
        "USER_INACTIVITY": "Ich habe keine Antwort erhalten. Ich beende diesen Anruf. Auf Wiedersehen."
    },
    "en": {
        "INPUT_LOST": "The microphone connection was interrupted. Further answers will not be sent. This call will end after the current request has finished.",
        "BUSY_AUDIO": "The last recording could not be accepted. Please wait until the current request has finished.",
        "BUSY_TEXT": "Your last answer was recognized but could not be sent. Please wait until the current request has finished.",
        "ASR_EMPTY": "I could not detect speech. Please repeat your answer.",
        "ASR_FAILED": "Speech recognition failed. Please repeat your answer.",
        "TURN_FAILED": "The voice conversation could not continue. Further answers will not be sent. Please end this call.",
        "LANGUAGE_RETRY": "Please choose a language.",
        "USER_INACTIVITY": "I have not received a response. I will end this call. Goodbye."
    }
}
_AUTHENTICATION_FIELDS = frozenset((
    'caller_identification_fields', 'enable_phone_number_based_identification',
    'enable_multifactor_authentication', 'auto_authenticate', 'disable_auth_v2',
    'primary_authentication_type', 'secondary_authentication_type',
    'step_up_authentication_type', 'primary_identification_type',
    'secondary_identification_type', 'require_auth_for_fallback_record_creation',
    'push_notification_max_polling_retries', 'voice_minutes_account_is_locked',
))
_REQUIRED = frozenset({'version', 'service_id', 'context_profile', 'language',
    'language_selection', 'tts', 'key_terms', 'prompt', 'vad', 'behavior'})


def _invalid():
    # Fixed error: never echo provider strings, transcript, policy, or secrets.
    raise ValueError('Invalid authorized assistant settings')


def _object(value, allowed, required=()):
    if (not isinstance(value, dict) or not set(required) <= value.keys()
            or value.keys() - set(allowed)):
        _invalid()
    return value


def _text(value, limit, *, empty=True):
    if (not isinstance(value, str) or len(value) > limit or (not empty and not value)
            or any(ord(c) < 32 and c not in '\t\n\r' for c in value)):
        _invalid()
    return value


def _language(value):
    _text(value, 64, empty=False)
    if value.lower() not in _GRANDFATHERED and not _LANGUAGE.fullmatch(value):
        _invalid()
    # RFC 5646 singleton extensions may each appear at most once.
    extensions = []
    for part in value.lower().split('-')[1:]:
        if part == 'x':
            break
        if len(part) == 1:
            if part in extensions:
                _invalid()
            extensions.append(part)
    return value


def _number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        _invalid()
    return value


def _strings(value, *, count, length):
    if not isinstance(value, list) or len(value) > count:
        _invalid()
    for item in value:
        _text(item, length, empty=False)
    return value


def _language_choice(value):
    """Normalize exact choices without altering transcripts or internal punctuation."""
    normalized = " ".join(value.casefold().split())
    while normalized and unicodedata.category(normalized[-1]).startswith("P"):
        normalized = normalized[:-1].rstrip()
    return normalized


def _validate_projection(value, service_id):
    _object(value, _REQUIRED | {'language_source', 'behavior_sources', 'notice_messages', 'phonemes'}, _REQUIRED)
    if type(value['version']) is not int or value['version'] != 1:
        _invalid()
    if value['service_id'] != service_id:
        _invalid()
    if not isinstance(value['context_profile'], str) or not _SYS_ID.fullmatch(value['context_profile']):
        _invalid()
    _language(value['language'])
    selection = _object(value['language_selection'], {'enabled', 'dtmf_enabled', 'mode', 'languages'},
                        {'enabled', 'dtmf_enabled', 'languages'})
    if type(selection['enabled']) is not bool or type(selection['dtmf_enabled']) is not bool:
        _invalid()
    if 'mode' in selection:
        _text(selection['mode'], 128)
    languages = selection['languages']
    if not isinstance(languages, list) or not 1 <= len(languages) <= 16:
        _invalid()
    codes, phrases = set(), set()
    for language in languages:
        _object(language, {'code', 'display_name', 'language_selection_prompt',
            'dtmf_language_selection_prompt', 'trigger_phrases', 'secondary_language_prompt'}, {'code'})
        code = _language(language['code']).casefold()
        if code in codes:
            _invalid()
        codes.add(code)
        if 'display_name' in language:
            _text(language['display_name'], 128)
        for key in ('language_selection_prompt', 'dtmf_language_selection_prompt', 'secondary_language_prompt'):
            if key in language and not (key == 'secondary_language_prompt' and language[key] is None):
                _text(language[key], 4000)
        for phrase in _strings(language.get('trigger_phrases', []), count=32, length=256):
            normalized = _language_choice(phrase)
            if not normalized or normalized in phrases:
                _invalid()
            phrases.add(normalized)
    if value['language'].casefold() not in codes:
        _invalid()
    for field in ('notice_messages', 'phonemes'):
        if field not in value:
            continue
        mapping = value[field]
        if not isinstance(mapping, dict) or len(mapping) > 16:
            _invalid()
        locale_codes = set()
        for code, entries in mapping.items():
            _language(code)
            normalized_code = code.casefold()
            if normalized_code not in codes or normalized_code in locale_codes:
                _invalid()
            locale_codes.add(normalized_code)
            if field == 'notice_messages':
                _object(entries, _NOTICE_CODES)
                for text in entries.values():
                    _text(text, 4000)
            else:
                if not isinstance(entries, list) or len(entries) > 256:
                    _invalid()
                for entry in entries:
                    _object(entry, {'word', 'phoneme'}, {'word', 'phoneme'})
                    _text(entry['word'], 128)
                    _text(entry['phoneme'], 256)
    tts = _object(value['tts'], {'voice_profile', 'voices'})
    if 'voice_profile' in tts:
        _text(tts['voice_profile'], 256)
    voices = tts.get('voices', {})
    if not isinstance(voices, dict) or len(voices) > 16:
        _invalid()
    voice_codes = set()
    for code, voice in voices.items():
        _language(code)
        if code.casefold() not in codes or code.casefold() in voice_codes:
            _invalid()
        voice_codes.add(code.casefold())
        _object(voice, {'voice_id', 'voice_gender'})
        for field in voice:
            _text(voice[field], 256)
    terms = value['key_terms']
    if not isinstance(terms, dict) or len(terms) > 16:
        _invalid()
    term_codes = set()
    for code, language_terms in terms.items():
        _language(code)
        if code.casefold() not in codes or code.casefold() in term_codes:
            _invalid()
        term_codes.add(code.casefold())
        _strings(language_terms, count=256, length=128)
    prompt = _object(value['prompt'], {'systemMessage', 'introduction'})
    for key, limit in (('systemMessage', 32768), ('introduction', 4000)):
        if key in prompt:
            _text(prompt[key], limit)
    vad = _object(value['vad'], {'confidence', 'min_volume', 'start_secs', 'stop_secs'})
    for key, maximum in (('confidence', 1), ('min_volume', 32768), ('start_secs', 20), ('stop_secs', 20)):
        if key in vad:
            _number(vad[key], 0, maximum)
    behavior = _object(value['behavior'], _BEHAVIOR_FIELDS)
    for item in behavior.values():
        _text(item, 4000)
    if behavior.get('max_call_duration_in_minutes', '') != '':
        try:
            duration = float(behavior['max_call_duration_in_minutes'])
        except ValueError:
            _invalid()
        if not math.isfinite(duration) or duration <= 0:
            _invalid()
    if 'language_source' in value and value['language_source'] not in ('configured', 'tts', 'native_default'):
        _invalid()
    if 'behavior_sources' in value:
        sources = _object(value['behavior_sources'], behavior.keys())
        if any(source not in ('configured', 'native_default') for source in sources.values()):
            _invalid()
    return deepcopy(value)


@dataclass
class CallSettings:
    """A validated projection and one mutable selected language for one call."""
    _projection: dict
    selected_language: str

    @classmethod
    def from_authorized_response(cls, data, service_id, agent_id):
        for identifier in (service_id, agent_id):
            if not isinstance(identifier, str) or not _SYS_ID.fullmatch(identifier):
                _invalid()
        if not isinstance(data, dict) or data.get('error'):
            _invalid()
        result = data.get('result')
        if not isinstance(result, dict):
            _invalid()
        if 'version' in result and (type(result['version']) is not int or result['version'] != 1):
            _invalid()
        agents = result.get('authorized_agents')
        if (not isinstance(agents, list) or not 1 <= len(agents) <= 256
                or any(not isinstance(item, str) or not _SYS_ID.fullmatch(item) for item in agents)
                or agent_id not in agents):
            _invalid()
        projection = _validate_projection(result.get('assistant_settings'), service_id)
        return cls(projection, projection['language'])

    @property
    def service_id(self):
        return self._projection['service_id']

    @property
    def primary_language(self):
        return self._projection['language']

    @property
    def language(self):
        return self.selected_language

    @property
    def context_profile(self):
        return self._projection['context_profile']

    @property
    def introduction(self):
        return self._projection['prompt'].get('introduction', '')

    @property
    def configured_goodbye(self):
        if self._projection.get('behavior_sources', {}).get('goodbye_message') != 'configured':
            return ''
        return self._projection['behavior'].get('goodbye_message', '')

    @property
    def selected_language_welcome(self):
        # Native secondary_language_prompt is a greeting after selection, not policy.
        if len(self._projection['language_selection']['languages']) < 2:
            return ''
        return self._current_language().get('secondary_language_prompt') or ''

    @property
    def configured_retry_prefix(self):
        if self._projection.get('behavior_sources', {}).get('retry_prefix') != 'configured':
            return ''
        return self._projection['behavior'].get('retry_prefix', '')

    @property
    def language_selection(self):
        return deepcopy(self._projection['language_selection'])

    @property
    def unsupported_language_selection(self):
        selection = self._projection['language_selection']
        return (selection['enabled'] and len(selection['languages']) > 1
                and selection.get('mode', '').strip().casefold() == 'dtmf')

    @property
    def selection_prompt(self):
        selection = self._projection['language_selection']
        if not self._voice_selection_enabled() or len(selection['languages']) < 2:
            return ''
        language = self._current_language()
        # This transport cannot consume DTMF; only advertise actionable speech.
        return language.get('language_selection_prompt', '')

    def _current_language(self):
        return next(item for item in self._projection['language_selection']['languages']
                    if item['code'].casefold() == self.selected_language.casefold())

    def native_context(self):
        # Match VoiceConversationManager's proven create-conversation fields.
        return {
            'interaction_requester_session_language': self.language,
            'interaction_user_language': self.language,
            'requester_session_language': self.language,
            'voice_assistant': self.service_id, 'interaction_ai_voice': 'true',
            'global_context_profile': self.context_profile,
        }

    def snapshot(self):
        return deepcopy(self._projection)

    def session_parameters(self):
        """Detached private settings; never an SDK DTO or Bot variable payload.

        Native prompt text is preserved verbatim. A language welcome is spoken
        by the session consumer after selection; it is not model instructions.
        Delivery modes need an explicit consumer; their presence is no claim
        that every model or local speech engine supports them. Authentication
        budgets remain native metadata and never retry ASR or business actions.
        native_projection retains the validated source for capability reporting.
        """
        behavior = self._projection['behavior']
        return {
            'version': 1, 'service_id': self.service_id,
            'context_profile': self.context_profile, 'language': self.language,
            'primary_language': self.primary_language,
            'prompt': {
                'systemMessage': self._projection['prompt'].get('systemMessage', ''),
                'introduction': self.introduction,
                'language_welcome': self.selected_language_welcome,
            },
            'delivery': {key: behavior.get(key, '')
                         for key in ('number_delivery', 'identifier_delivery')},
            'timing': {
                'vad_start_ms': self.vad_start_ms, 'vad_stop_ms': self.vad_stop_ms,
                'inactivity_seconds': self.inactivity_seconds,
                'filler_delay_seconds': self.filler_delay_seconds,
                'max_call_seconds': self.max_call_seconds,
            },
            'retry': {
                'configured_prefix': self.configured_retry_prefix,
                'native_authentication_max_retries': behavior.get('voice_max_retries', ''),
                'classification': 'native_authentication_metadata',
                'local_retry_enabled': False,
            },
            'authentication': {key: item for key, item in behavior.items()
                               if key in _AUTHENTICATION_FIELDS},
            'native_projection': self.snapshot(),
        }

    def notice_text(self, code):
        """Use an exact configured locale notice or an owned de/en translation."""
        if not isinstance(code, str) or code not in _NOTICE_CODES:
            return ''
        configured = self._projection.get('notice_messages', {})
        messages = next((messages for language, messages in configured.items()
                         if language.casefold() == self.language.casefold()), {})
        if code in messages:
            return messages[code]
        if (code == 'USER_INACTIVITY'
                and self.language.casefold() == self.primary_language.casefold()
                and self._projection.get('behavior_sources', {}).get('goodbye_message') == 'configured'):
            # A global custom text belongs to the configured primary locale.
            # Never replay it after a secondary language was selected.
            return self.configured_goodbye
        base_language = self.language.split('-', 1)[0].casefold()
        return _NOTICE_MESSAGES.get(base_language, {}).get(code, '')

    def _voice_selection_enabled(self):
        selection = self._projection['language_selection']
        return selection['enabled'] and selection.get('mode', '').strip().casefold() != 'dtmf'

    def select_language(self, text):
        if not self._voice_selection_enabled() or not isinstance(text, str) or len(text) > 4000:
            return False
        normalized = _language_choice(text)
        for item in self._projection['language_selection']['languages']:
            if any(_language_choice(phrase) == normalized for phrase in item.get('trigger_phrases', [])):
                self.selected_language = item['code']
                return True
        return False

    def select_dtmf(self, digit):
        # The projection has prompts, not a proven digit-to-language contract.
        # Do not infer a mapping from language ordering or natural-language text.
        return False

    def asr_context(self):
        terms = next((value for code, value in self._projection['key_terms'].items()
                      if code.casefold() == self.language.casefold()), [])
        return {'language': self.language.split('-', 1)[0].lower(), 'terms': list(terms)}

    @property
    def vad_start_ms(self):
        value = self._projection['vad'].get('start_secs')
        return round(value * 1000) if value is not None and .02 <= value <= 2 else None

    @property
    def vad_stop_ms(self):
        value = self._projection['vad'].get('stop_secs')
        return round(value * 1000) if value is not None and .2 <= value <= 2 else None

    def _supported_seconds(self, key):
        value = self._projection['behavior'].get(key)
        try:
            seconds = float(value) if value else None
        except ValueError:
            return None
        return seconds if seconds is not None and math.isfinite(seconds) and 0 < seconds <= 3600 else None

    @property
    def inactivity_seconds(self):
        return self._supported_seconds('user_inactivity_threshold_in_seconds')

    @property
    def filler_delay_seconds(self):
        return self._supported_seconds('filler_message_delay_in_seconds')

    @property
    def max_call_seconds(self):
        value = self._projection['behavior'].get('max_call_duration_in_minutes')
        # Retain the existing host's one-hour policy ceiling; callers also apply
        # their operator's potentially stricter configured call duration.
        return min(float(value), 60) * 60 if value else None

    @property
    def unsupported_metadata(self):
        vad = {key: value for key, value in self._projection['vad'].items()
               if key in ('confidence', 'min_volume')
               or key == 'start_secs' and self.vad_start_ms is None
               or key == 'stop_secs' and self.vad_stop_ms is None}
        behavior = {key: value for key, value in self._projection['behavior'].items()
                    if key == 'filler_message_delay_in_seconds'
                    or key == 'user_inactivity_threshold_in_seconds' and self._supported_seconds(key) is None}
        sources = self._projection.get('behavior_sources', {})
        unlocalized = [key for key in ('retry_prefix', 'goodbye_message')
                       if sources.get(key) == 'native_default']
        dtmf_prompts = {item['code']: item['dtmf_language_selection_prompt']
                        for item in self._projection['language_selection']['languages']
                        if item.get('dtmf_language_selection_prompt')}
        metadata = {'tts': deepcopy(self._projection['tts']), 'vad': vad,
                    'behavior': behavior, 'dtmf_language_mapping': 'unsupported',
                    'dtmf_language_selection_prompts': dtmf_prompts,
                    'unlocalized_native_defaults': unlocalized}
        if 'phonemes' in self._projection:
            # Native phonetic entries have no proven local TTS conversion.
            metadata['phonemes'] = deepcopy(self._projection['phonemes'])
        mode = self._projection['language_selection'].get('mode', '')
        if mode.strip().casefold() == 'dtmf':
            metadata['language_input_mode'] = mode
        return metadata

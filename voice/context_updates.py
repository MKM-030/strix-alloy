"""Bounded raw caller context for the installed synchronous VA control action.

An empty platform response can become status=success in the installed response
builder. That acknowledgement never proves persistence or agent ingestion.
"""


class ContextRequestAliases:
    """Only locally dispatched context IDs may follow one business request."""
    def __init__(self):
        self._requests = {}

    def bind(self, control_request_id, business_request_id):
        if len(self._requests) >= 32 or control_request_id in self._requests:
            raise RuntimeError('Context callback alias limit reached')
        self._requests[control_request_id] = business_request_id

    def resolve(self, wire_request_id, current_business_request_id):
        if type(wire_request_id) is not str or not current_business_request_id:
            return None
        if wire_request_id == current_business_request_id:
            return current_business_request_id
        if self._requests.get(wire_request_id) == current_business_request_id:
            return current_business_request_id
        return None

    def clear(self):
        self._requests.clear()


def validate_update(data, *, previous_revision, previous_text):
    if type(data) is not dict or set(data) - {'revision', 'caller_updates', 'voice_context'}:
        raise ValueError('Invalid context update fields')
    revision, text = data.get('revision'), data.get('caller_updates')
    if type(revision) is not int or not 1 <= revision <= 2147483647:
        raise ValueError('Invalid caller context revision')
    if (type(text) is not str or not text.strip() or len(text) > 8000
            or len(text.encode('utf-8')) > 12000):
        raise ValueError('Caller context exceeds bounded raw snapshot')
    if revision <= previous_revision:
        raise RuntimeError('Caller context revision is stale or already attempted')
    if not text.startswith(previous_text) or text == previous_text:
        raise ValueError('Caller context must append to the session snapshot')
    return revision, text


def update_payload(*, request_id, client_session_id, user_id, app_inbound_id,
                   email_id, now_session_id, native_context, revision, text):
    context = dict(native_context)
    context['scc_voice_caller_updates'] = text
    context['scc_voice_caller_revision'] = str(revision)
    payload = {'requestId': request_id, 'clientSessionId': client_session_id,
        'userId': user_id, 'appInboundId': app_inbound_id, 'emailId': email_id,
        'action': 'UPDATE_CONTEXT_VARS',
        'message': {'text': '', 'typed': True, 'clientMessageId': request_id},
        'contextVariables': context}
    if now_session_id:
        payload['nowSessionId'] = now_session_id
    return payload


def action_acknowledged(value):
    if type(value) is not dict or value.get('error'):
        return False
    result = value.get('result')
    if type(result) is dict and result.get('error'):
        return False
    status = value.get('status')
    if status is None and type(result) is dict:
        status = result.get('status')
    return status == 'success'

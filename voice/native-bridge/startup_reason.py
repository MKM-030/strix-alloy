"""Nonsecret startup diagnostics; no routing, retries or native side effects.

Access denial must be supplied as a typed reason by a trusted structural owner.
No callback shape is assumed here; arbitrary error/bot text never proves denial.
"""
import asyncio


KNOWN_MESSAGES = {
    'Configured initial topic is not offered by ServiceNow': 'servicenow_initial_topic_not_offered',
    'Configured initial topic did not reach its input control': 'servicenow_initial_topic_input_not_reached',
    'ServiceNow conversation startup timed out': 'servicenow_startup_deadline',
    'ServiceNow greeting failed': 'servicenow_startup_callback_failed',
    'ServiceNow conversation is not ready': 'servicenow_startup_not_ready',
    'ServiceNow conversation is disabled': 'servicenow_disabled',
    'ServiceNow conversation bridge unavailable': 'servicenow_bridge_unavailable',
    'ServiceNow conversation binding changed': 'servicenow_conversation_binding_changed',
    'Invalid owned startup result': 'servicenow_invalid_startup_result',
}
REASONS = frozenset(KNOWN_MESSAGES.values()) | {
    'servicenow_access_denied', 'servicenow_transport_deadline',
    'servicenow_startup_cancelled', 'servicenow_startup_failed',
}


class NativeStartupError(RuntimeError):
    """For a future confirmed structural signal, never a text-derived guess."""

    def __init__(self, reason):
        if type(reason) is not str or reason not in REASONS:
            raise ValueError('Unknown native startup reason')
        self.reason_code = reason
        super().__init__(reason)


def startup_reason(error):
    """Classify bounded explicit causes without rendering exceptions or payloads."""
    seen, fallback = set(), None
    for _ in range(8):
        if not isinstance(error, BaseException) or id(error) in seen:
            break
        seen.add(id(error))
        if isinstance(error, NativeStartupError) and error.reason_code in REASONS:
            return error.reason_code
        if isinstance(error, asyncio.CancelledError):
            return 'servicenow_startup_cancelled'
        if isinstance(error, TimeoutError):
            return 'servicenow_transport_deadline'
        if (fallback is None and isinstance(error, (RuntimeError, ValueError))
                and len(error.args) == 1 and type(error.args[0]) is str):
            fallback = KNOWN_MESSAGES.get(error.args[0])
        # Explicit chaining denotes an intentional causal relation. Do not guess
        # from an unrelated implicit exception context or any free-form text.
        error = error.__cause__
    return fallback or 'servicenow_startup_failed'


async def open_with_startup_diagnostics(dialog, logger, call_id):
    """Observe the existing single open; propagate its exact result/error/cause."""
    try:
        return await dialog.open()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        try:
            logger.warning('Voice startup call=%s stage=dialog_open_failed reason=%s type=%s',
                           call_id, startup_reason(error), type(error).__name__)
        except Exception:
            # Diagnostics cannot replace or suppress the original startup error.
            pass
        raise

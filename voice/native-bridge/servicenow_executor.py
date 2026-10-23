"""Owned legacy VA adapter. Reply text is not authoritative business completion."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutorCapabilities:
    independent_context: bool = False
    checkpoints: bool = False
    status_lookup: bool = False
    durable_execution: bool = False
    authoritative_idempotency: bool = False
    version_fence: bool = False
    cancel_before_commit: bool = False
    compensate_after_commit: bool = False


class LegacyVAExecutor:
    capabilities = ExecutorCapabilities()

    def __init__(self, dialog, *, ready=None):
        self.dialog = dialog
        self.ready = ready

    async def wait_ready(self):
        if self.ready is not None:
            await self.ready.wait()

    async def turn(self, operation, on_reply):
        return await self.dialog.turn(operation['text'], on_reply=on_reply,
                                      voice_context=operation['voice_context'])

    async def close(self):
        await self.dialog.close()
        # Dialog.close intentionally catches failed END; ownership lasts until ACK.
        if getattr(self.dialog, 'must_reset', False):
            await self.dialog.wait_owned_cleanup()
        if getattr(self.dialog, 'must_reset', False):
            raise RuntimeError('owned cleanup not acknowledged')

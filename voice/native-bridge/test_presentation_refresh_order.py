"""CPU-only potential native mutation at refresh/START, not its proven Java cause.

The saved REST probe proved same-caller/Guest metadata sharing without Voice.
These synthetic mutators test the local ordering hazard while preserving the
original business session identity and the existing credential deadline.
"""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice import bridge
from voice.tests import test_local_caller_create as owned
from test_presentation_attestation import NONCE, receipt

CANONICAL_ALIAS = 'voice-' + 'b' * 32


class RefreshGrantOrderTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = owned.OwnedCreateBridgeTests.asyncSetUp
    start = owned.OwnedCreateBridgeTests.start
    settle = owned.OwnedCreateBridgeTests.settle

    async def scenario(self, *, start_mutates=False):
        self.bridge.settings.presentation_history_enabled = True
        entered, release, issued = asyncio.Event(), asyncio.Event(), asyncio.Event()
        native = {}
        canonical = {'alias': None}
        events = []

        async def issue(*args, **kwargs):
            payload = args[3]
            events.append('grant')
            issued.set()
            alias = canonical['alias'] or payload['userId']
            native[alias] = payload['nonceSha256']
            return dict(receipt(payload), providerContextUserId=alias)

        async def refresh(*args, **kwargs):
            events.append('refresh_enter')
            entered.set()
            await release.wait()
            # A potential native rebinding/reset, not a claim about its writer.
            native.clear()
            canonical['alias'] = CANONICAL_ALIAS
            events.append('refresh_complete')

        self.refresher.side_effect = refresh
        issuer = AsyncMock(side_effect=issue)
        self.enterContext(patch('voice.bridge.issue_presentation_grant', issuer))
        self.enterContext(patch('voice.bridge.secrets.token_hex', return_value=NONCE))
        original_send = self.bridge.send

        async def send(*args, **kwargs):
            if len(args) >= 4 and args[3] == 'START_CREATED_CONVERSATION':
                events.append('start')
                if start_mutates:
                    native.clear()
            return await original_send(*args, **kwargs)

        self.enterContext(patch.object(self.bridge, 'send', side_effect=send))
        try:
            self.assertEqual((await self.start()).status, 202)
            await asyncio.wait_for(entered.wait(), .5)
            early = issued.is_set()
        finally:
            release.set()
        await self.settle()
        session = next(iter(self.bridge.sessions.values()))
        task = session.presentation_task
        if task:
            await asyncio.wait_for(asyncio.shield(task), .5)
        return session, issuer, events, native, early

    async def test_refresh_cannot_rebind_or_clear_a_grant_issued_before_it_finishes(self):
        session, issuer, events, native, early = await self.scenario()
        self.assertFalse(early, 'Optional grant must not dispatch while its owned refresh is unfinished')
        self.assertLess(events.index('refresh_complete'), events.index('grant'))
        self.assertIn(CANONICAL_ALIAS, native, 'The post-refresh canonical grant must remain available')
        issuer.assert_awaited_once()
        self.assertFalse(session.failed)

    async def test_normal_start_dispatch_cannot_clear_an_already_admitted_optional_grant(self):
        _, issuer, events, native, _ = await self.scenario(start_mutates=True)
        self.assertLess(events.index('start'), events.index('grant'))
        self.assertIn(CANONICAL_ALIAS, native)
        issuer.assert_awaited_once()

    async def test_server_alias_is_private_and_never_rewrites_original_business_identity(self):
        session, issuer, _, _, _ = await self.scenario()
        payload = issuer.await_args.args[3]
        self.assertEqual(session.user_id, 'voice-' + session.sid)
        self.assertEqual(payload['userId'], session.user_id)
        self.assertEqual(payload['clientSessionId'], session.sid)
        self.assertNotIn('providerContextUserId', payload, 'The grant issuer derives canonical alias itself')
        self.assertEqual(self.sent[0]['userId'], session.user_id)
        self.assertEqual(getattr(session, 'presentation_provider_user_id', None), CANONICAL_ALIAS)
        self.assertEqual(session.presentation_nonce, NONCE)
        self.assertNotIn(CANONICAL_ALIAS, repr(session))

    async def test_early_publication_before_start_is_unavailable_without_store_or_grant_dispatch(self):
        from test_presentation_history import PresentationContractTests
        self.bridge.settings.presentation_history_enabled=True
        entered,release=asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):
            entered.set();await release.wait()
        self.refresher.side_effect=refresh
        issuer=AsyncMock(side_effect=lambda *args,**kwargs:dict(receipt(args[3]),providerContextUserId=CANONICAL_ALIAS))
        self.enterContext(patch('voice.bridge.issue_presentation_grant',issuer))
        self.assertEqual((await self.start()).status,202)
        await asyncio.wait_for(entered.wait(),.5)
        session=next(iter(self.bridge.sessions.values()))
        try:
            self.assertIsNone(session.presentation_task)
            response=await self.ui.post('/api/presentation-history',json=PresentationContractTests().event(),headers=self.headers)
            self.assertEqual(response.status,200)
            self.assertEqual(await response.json(),{'state':'presentation_history_unavailable','stored':False})
            issuer.assert_not_awaited();self.assertEqual(self.sent,[])
            self.assertFalse(session.presentation_disabled);self.assertFalse(session.failed)
            self.assertEqual(session.presentation_sequence,0)
        finally:
            release.set()
        await self.settle()
        if session.presentation_task:await session.presentation_task
        issuer.assert_awaited_once()
        self.assertEqual([item.get('action') for item in self.sent],['START_CREATED_CONVERSATION'])
        self.assertFalse(session.failed)

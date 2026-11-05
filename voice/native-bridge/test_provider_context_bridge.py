"""CPU-only canonical context authority independent of optional history."""
import asyncio
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from voice import bridge
from voice.caller_binding import ProviderContextBinding
from voice.tests import test_local_caller_create as owned
import test_context_updates as context_fixtures
ALIAS='voice-'+'e'*32

def binding(owner, session):
    b=session.conversation_binding
    return ProviderContextBinding(owner.settings.caller_binding_service_id,
        session.voice_context['global_context_profile'],b.conversation_id,b.interaction_id,
        b.creation_message_id,session.caller_user_id,ALIAS)

class ProviderRefreshBridgeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=owned.OwnedCreateBridgeTests.asyncSetUp
    start=owned.OwnedCreateBridgeTests.start
    settle=owned.OwnedCreateBridgeTests.settle
    async def test_history_disabled_still_adopts_private_context_without_business_identity_change(self):
        async def refresh(*args,**kwargs):
            self.assertTrue(kwargs['provider_context'])
            session=next(iter(self.bridge.sessions.values()))
            return binding(self.bridge,session)
        self.refresher.side_effect=refresh
        self.assertFalse(self.bridge.settings.presentation_history_enabled)
        self.assertEqual((await self.start()).status,202);await self.settle()
        session=next(iter(self.bridge.sessions.values()))
        self.assertEqual(session.provider_context_binding.provider_user_id,ALIAS)
        self.assertNotIn(ALIAS,repr(session));self.assertEqual(session.user_id,'voice-'+session.sid)
        self.assertEqual(self.sent[0]['userId'],session.user_id)
        self.assertIsNone(session.presentation_task)
        self.bridge.retire_caller_bootstrap(session)
        self.assertIsNone(session.provider_context_binding)
    async def optional_start(self, result):
        self.refresher.return_value=result
        self.assertEqual((await self.start()).status,202);await self.settle()
        session=next(iter(self.bridge.sessions.values()))
        self.assertFalse(session.failed);self.assertIsNone(session.provider_context_binding)
        self.assertEqual(self.sent[0]['userId'],session.user_id)
    async def test_absent_optional_binding_preserves_start(self):
        await self.optional_start(None)
    async def test_invalid_optional_binding_preserves_start(self):
        await self.optional_start({'provider_user_id':ALIAS})
    async def test_replaced_session_during_refresh_cannot_bind_or_start(self):
        async def refresh(*args,**kwargs):
            session=next(iter(self.bridge.sessions.values()));result=binding(self.bridge,session)
            self.bridge.sessions[session.sid]=bridge.Conversation(sid=session.sid)
            return result
        self.refresher.side_effect=refresh
        self.assertEqual((await self.start()).status,202);await self.settle()
        session=next(iter(self.bridge.sessions.values()))
        self.assertIsNone(session.provider_context_binding);self.assertEqual(self.sent,[])
    async def test_changed_caller_during_refresh_cannot_bind_or_start(self):
        async def refresh(*args,**kwargs):
            session=next(iter(self.bridge.sessions.values()));result=binding(self.bridge,session)
            session.caller_user_id='f'*32
            return result
        self.refresher.side_effect=refresh
        self.assertEqual((await self.start()).status,202);await self.settle()
        session=next(iter(self.bridge.sessions.values()))
        self.assertIsNone(session.provider_context_binding);self.assertTrue(session.failed)
        self.assertEqual(self.sent,[])
    async def test_changed_source_during_refresh_never_adopts_or_starts(self):
        async def refresh(*args,**kwargs):
            session=next(iter(self.bridge.sessions.values()));result=binding(self.bridge,session)
            self.bridge.bot_url += '/changed'
            return result
        self.refresher.side_effect=refresh
        self.assertEqual((await self.start()).status,202);await self.settle()
        session=next(iter(self.bridge.sessions.values()))
        self.assertIsNone(session.provider_context_binding);self.assertTrue(session.failed)
        self.assertEqual(self.sent,[])

class ProviderContextLaneTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=context_fixtures.ContextLaneTests.asyncSetUp
    asyncTearDown=context_fixtures.ContextLaneTests.asyncTearDown
    post=context_fixtures.ContextLaneTests.post
    async def test_missing_binding_is_local_only_without_delaying_business(self):
        self.session.provider_context_binding=None;self.session.provider_context_identity=None
        response=await self.post({'revision':1,'caller_updates':'Lieferort ist Dresden.'})
        self.assertEqual(response.status,200);result=await response.json()
        self.assertFalse(result['contextStored']);self.assertTrue(result['queuedOnly'])
        self.assertEqual(self.received,[]);self.assertTrue(self.session.busy)
    async def test_status_reuses_canonical_metadata_alias_and_refuses_stale_scope(self):
        self.release.set()
        await self.post({'revision':1,'caller_updates':'Lieferort ist Dresden.'})
        response=await self.ui.get('/api/context-status?revision=1',headers=self.headers)
        # This store-only fixture deliberately lacks a prompt-status receipt.
        self.assertEqual(response.status,502)
        self.assertEqual(self.received[-1]['operation'],'status')
        self.assertEqual(self.received[-1]['userId'],self.session.provider_context_binding.provider_user_id)
        self.assertEqual(self.received[-1]['clientSessionId'],self.session.sid)
        self.session.provider_context_identity=('stale',)
        prior=len(self.received)
        response=await self.ui.get('/api/context-status?revision=1',headers=self.headers)
        self.assertEqual(response.status,409);self.assertEqual(len(self.received),prior)
    async def test_stale_optional_owner_never_dispatches_metadata(self):
        self.session.provider_context_identity=('stale',)
        response=await self.post({'revision':1,'caller_updates':'Lieferort ist Dresden.'})
        self.assertFalse((await response.json())['contextStored']);self.assertEqual(self.received,[])
    async def test_metadata_uses_canonical_alias_and_original_transport_id(self):
        self.release.set()
        response=await self.post({'revision':1,'caller_updates':'Lieferort ist Dresden.'})
        self.assertTrue((await response.json())['contextStored'])
        self.assertEqual(self.received[0]['userId'],self.session.provider_context_binding.provider_user_id)
        self.assertNotEqual(self.received[0]['userId'],self.session.user_id)
        self.assertEqual(self.received[0]['clientSessionId'],self.session.sid)
if __name__=='__main__':unittest.main()

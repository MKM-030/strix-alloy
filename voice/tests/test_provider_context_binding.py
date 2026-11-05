"""Independent optional binding never widens required refresh authority."""
import dataclasses
import json
import unittest
import test_native_caller_authority as wire
from test_native_caller_authority import SERVICE, AGENT, PROFILE, TOKEN
from voice.caller_binding import CallerBinding, refresh_native_caller_session

ALIAS = 'voice-'+'e'*32
class ProviderContextWireTests(wire.NativeRefreshWireTests):
    def descriptor(self):
        return dict(version=1,status='available',service_id=SERVICE,context_profile=PROFILE,
            **self.owned,caller_user_id='1'*32,provider_user_id=ALIAS)
    async def refresh_context(self, optional):
        data=self.acknowledgement()
        if optional is not None:data['result']['provider_context_binding']=optional
        return await refresh_native_caller_session('https://instance.example.test',SERVICE,AGENT,PROFILE,
            TOKEN,dict(self.owned),CallerBinding('1'*32,'actual.email@example.test'),provider_context=True,
            http_factory=self.factory(raw=json.dumps(data).encode()))
    async def test_independent_private_frozen_binding_and_opt_in(self):
        source=self.descriptor();bound=await self.refresh_context(source)
        self.assertEqual(bound.provider_user_id,ALIAS)
        self.assertEqual(self.sent[0][1]['json']['providerContextVersion'],1)
        self.assertNotIn(ALIAS,repr(bound))
        source['provider_user_id']='voice-'+'f'*32
        self.assertEqual(bound.provider_user_id,ALIAS)
        with self.assertRaises(dataclasses.FrozenInstanceError):bound.provider_user_id='changed'
    async def test_missing_unavailable_and_malformed_optional_binding_preserve_required_refresh(self):
        invalid=[None,{},dict(version=1,status='unavailable'),dict(version=1,status='available')]
        for key in self.descriptor():
            bad=self.descriptor();bad[key]=True if key=='version' else 'bad';invalid.append(bad)
        bad=self.descriptor();bad['extra']='bad';invalid.append(bad)
        for optional in invalid:
            with self.subTest(optional=optional):self.assertIsNone(await self.refresh_context(optional))
            self.assertEqual(len(self.sent),1)
if __name__=='__main__':unittest.main()

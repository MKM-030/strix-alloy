import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('VOICE_PORTABLE_SOURCE_ROOT',Path(__file__).resolve().parents[2]))
STUDIO = SOURCE/'voice/voice-studio'
sys.path.insert(0,str(STUDIO))
sys.path.append(str(Path(os.environ.get('VOICE_PORTABLE_SUPPORT_ROOT',SOURCE))/'voice/voice-studio'))

def load(name, source):
    spec=importlib.util.spec_from_file_location(name,source)
    result=importlib.util.module_from_spec(spec)
    sys.modules[name]=result
    spec.loader.exec_module(result)
    return result

launcher=load('portable_studio_launch',STUDIO/'launch_studio.py')
server=load('portable_studio_server',STUDIO/'studio_server.py')
startup=load('portable_native_start',SOURCE/'voice/native-start/start_services.py')

class StudioLaunchOriginTests(unittest.TestCase):
    def test_target_origin_reaches_the_server_arguments(self):
        with patch.dict(os.environ,{'SCC_VOICE_STUDIO_ORIGIN':'https://voice.customer.example'},clear=True):
            args=launcher.arguments()
        self.assertEqual(args[args.index('--origin')+1],'https://voice.customer.example')

    def test_missing_origin_never_falls_back_to_source_host(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError): launcher.arguments()

    def test_invalid_origins_are_rejected_before_startup(self):
        for value in ['', 'http://voice.customer.example','https://user:pass@voice.customer.example',
                'https://voice.customer.example/path','https://voice.customer.example?next=evil',
                'https://voice.customer.example#frag','https://voice.customer.example\\@evil.test',
                'https://voice.customer.example\n','https://voice.customer.example:65536',
                'https://voice.customer.example:0','https://0x7f000001','https://127.000.0.1',
                'https://voice..customer.example','https://voice.customer.example.']:
            with self.subTest(value=value),patch.dict(os.environ,{'SCC_VOICE_STUDIO_ORIGIN':value},clear=True):
                with self.assertRaises(ValueError): launcher.arguments()

    def test_origin_is_canonical_for_browser_csrf_matching(self):
        with patch.dict(os.environ,{'SCC_VOICE_STUDIO_ORIGIN':'https://Voice.Customer.Example:8443/'},clear=True):
            args=launcher.arguments()
        self.assertEqual(args[args.index('--origin')+1],'https://voice.customer.example:8443')

    def test_default_https_port_matches_browser_origin_serialization(self):
        with patch.dict(os.environ,{'SCC_VOICE_STUDIO_ORIGIN':'https://voice.customer.example:443/'},clear=True):
            args=launcher.arguments()
        self.assertEqual(args[args.index('--origin')+1],'https://voice.customer.example')

    def test_explicit_cli_origin_wins_over_environment_in_status_arguments(self):
        seen=[]
        class Owner:
            def owned_listener(self,port,args):seen.extend(args);return None
        with patch.object(sys,'argv',['launch_studio.py','status','--origin','https://explicit.customer.example']),\
                patch.dict(os.environ,{'SCC_VOICE_STUDIO_ORIGIN':'https://environment.customer.example'},clear=True),\
                patch.object(launcher,'owner_tools',return_value=Owner()),patch.object(launcher.Path,'home',return_value=Path('C:/test-home')),contextlib.redirect_stdout(io.StringIO()):
            try: result=launcher.main()
            except SystemExit: self.fail('Studio CLI does not yet support explicit origin')
        self.assertEqual(result,0)
        self.assertEqual(seen[seen.index('--origin')+1],'https://explicit.customer.example')

    def test_server_rejects_ambiguous_origin_before_loading_private_files(self):
        for value in ['https://voice.customer.example\n','https://voice.customer.example:65536',
                      'https://0x7f000001','https://voice..customer.example']:
            with self.subTest(value=value),tempfile.TemporaryDirectory() as folder:
                config=server.Config(origin=value,runtime=Path(folder),profile_root=Path(folder)/'profiles')
                try:
                    with self.assertRaises(ValueError): server.create_app(config,manager=object())
                except FileNotFoundError:
                    self.fail('Invalid origin reached private-file reads')

class NativeConfigSelectionTests(unittest.TestCase):
    def configs(self,folder):
        bot=folder/'operator-bridge.json';bot.write_text('{}')
        native=folder/'operator-native.json';native.write_text(json.dumps({'auth_mode':'servicenow'}))
        return bot,native

    def voice_start(self):
        with patch.object(startup,'start_python') as start:
            try: startup.voice_start(object())
            except FileNotFoundError:self.fail('Source-local default was used instead of selected config')
        return start.call_args_list

    def test_operator_configs_are_passed_to_each_actual_service(self):
        with tempfile.TemporaryDirectory() as folder:
            bot,native=self.configs(Path(folder))
            with patch.dict(os.environ,{'SCC_VOICE_BOT_CONFIG':str(bot),'SCC_VOICE_NATIVE_CONFIG':str(native)},clear=True):
                calls=self.voice_start()
        self.assertEqual(calls[0].args[3],bot)
        self.assertEqual(calls[1].args[3],native)

    def test_missing_config_fails_before_starting_any_service(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'SCC_VOICE_BOT_CONFIG':str(Path(folder)/'missing'),'SCC_VOICE_NATIVE_CONFIG':str(Path(folder)/'missing2')},clear=True),\
                    patch.object(startup,'start_python') as start:
                try:
                    with self.assertRaises(RuntimeError):startup.voice_start(object())
                except FileNotFoundError:self.fail('Missing selected config was not preflighted')
            start.assert_not_called()

    def test_selected_development_auth_profile_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            bot,native=self.configs(Path(folder));native.write_text(json.dumps({'auth_mode':'development'}))
            with patch.dict(os.environ,{'SCC_VOICE_BOT_CONFIG':str(bot),'SCC_VOICE_NATIVE_CONFIG':str(native)},clear=True),\
                    patch.object(startup,'start_python') as start:
                try:
                    with self.assertRaises(RuntimeError):startup.voice_start(object())
                except FileNotFoundError:self.fail('Selected authentication profile was not inspected')
            start.assert_not_called()

    def test_explicit_config_arguments_win_over_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            bot,native=self.configs(Path(folder))
            with patch.dict(os.environ,{'SCC_VOICE_BOT_CONFIG':'missing','SCC_VOICE_NATIVE_CONFIG':'missing'},clear=True),\
                    patch.object(startup,'start_python') as start:
                try:startup.voice_start(object(),bot_config=bot,native_config=native)
                except TypeError:self.fail('Native coordinator does not yet accept explicit selected config paths')
            self.assertEqual(start.call_args_list[0].args[3],bot)
            self.assertEqual(start.call_args_list[1].args[3],native)

if __name__=='__main__':unittest.main()

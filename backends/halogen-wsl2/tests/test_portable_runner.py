import copy
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = load('guard', ROOT / 'scripts/guard-halogen-startup.py')
        self.assertTrue(hasattr(self.guard, 'configure_target'), 'guard lacks portable target admission')
        self.guard.configure_target('Other-Distro', 'alice', '/home/alice/model files', '/mnt/c/package files', '/opt/dxg.so')
        self.cid = 'a' * 64
        self.info = dict(Id=self.cid, Name='/halogen-flash-hybrid-test', State=dict(Running=True),
            Config=dict(Image=self.guard.IMAGE, Labels={'halogen.performance':'hybrid','strix-alloy.owner':'strix-alloy-wsl2','strix-alloy.run':'halogen-flash-hybrid-test'}),
            HostConfig=dict(Memory=47244640256, MemorySwap=47244640256),
            Mounts=[dict(Source=source, Destination=dest, RW=False, Type='bind') for dest, source in self.guard.EXPECTED_MOUNTS.items()],
            NetworkSettings=dict(Ports={'8731/tcp':[dict(HostIp='127.0.0.1',HostPort='8731')]}))

    def test_selected_identity_is_forwarded(self):
        self.assertEqual(self.guard.WSL[:7], ['wsl.exe','-d','Other-Distro','-u','alice','--exec','docker'])
        self.guard.validate_target(self.info, self.cid)

    def test_mismatched_id_image_or_mount_is_rejected(self):
        for target in ['Id','Image','RW','Source','Memory']:
            with self.subTest(target=target):
                info=copy.deepcopy(self.info)
                if target=='Id': info['Id']='b'*64
                elif target=='Image': info['Config']['Image']='unpinned:latest'
                elif target=='Memory': info['HostConfig']['Memory']=1
                elif target=='RW': info['Mounts'][0]['RW']=True
                else: info['Mounts'][0]['Source']='/wrong'
                with self.assertRaises(ValueError): self.guard.validate_target(info,self.cid)

    def test_nested_mount_and_public_port_refused(self):
        self.info['Mounts'].append(dict(Source='/wrong',Destination='/workspace/bin',RW=False))
        with self.assertRaises(ValueError): self.guard.validate_target(self.info,self.cid)
        self.info['Mounts'].pop()
        self.info['NetworkSettings']['Ports']['8731/tcp'][0]['HostIp']='0.0.0.0'
        with self.assertRaises(ValueError): self.guard.validate_target(self.info,self.cid)

class ServeTests(unittest.TestCase):
    def test_only_qualified_health_can_begin_serving(self):
        path=ROOT/'tools/qualification/serve32k.py'
        self.assertTrue(path.exists(),'bounded serving probe is missing')
        serve=load('serve',path)
        health=dict(status='ok',version=dict(match=True),prompt_cache=dict(enabled=False),context=32768,slot_ctx=32768,kv_pool_positions=32768,slots=1)
        serve.check_health(health)
        for key,value in [('status','loading'),('context',262144),('slots',3),('version',dict(match=False)),('prompt_cache',dict(enabled=True))]:
            wrong=copy.deepcopy(health); wrong[key]=value
            with self.assertRaises(ValueError): serve.check_health(wrong)

if __name__=='__main__': unittest.main()

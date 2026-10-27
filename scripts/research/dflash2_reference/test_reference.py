import sys,unittest
from unittest.mock import patch
if __package__:
 from . import reference as r,weights,context_kv,backbone,proposal
else:import reference as r,weights,context_kv,backbone,proposal
class Assembly(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import torch
  cls.t=torch;torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.set_grad_enabled(False)
 def fixture(self,n=2,block=4):
  t=self.t;data={key:object() for key in weights.expected_header()}
  x=t.zeros((n,12800),device='cpu',dtype=t.bfloat16);pos=t.arange(n,device='cpu',dtype=t.int64)
  embed=t.zeros((block,2560),device='cpu',dtype=t.bfloat16)
  head=t.zeros((1,2560),device='cpu',dtype=t.bfloat16).expand(248320,-1)
  target=r.TargetEvidence('actual-target','pinned-revision','1'*64,'2'*64,'3'*64)
  owner=context_kv.OwnerMetadata(*([bytes([1])*32]*4),generation=1,round=1)
  return data,x,pos,embed,dict(anchor_token_id=9,head_weight=head,target=target,owner=owner,block_size=block,org_vocab_size=248077)
 def test_exact_subsets_positions_and_component_order(self):
  t=self.t;data,x,pos,embed,kw=self.fixture();events=[];hidden=t.ones((4,2560),device='cpu',dtype=t.bfloat16)
  class Private:
   k=t.zeros((5,2,8,128),device='cpu',dtype=t.bfloat16)
   v=k.clone()
  def context(a,b,w,*,owner):
   self.assertIs(a,x);self.assertIs(b,pos);self.assertEqual(set(w),set(context_kv.WEIGHT_SHAPES));events.append('context');return Private()
  def body(a,qp,k,v,cp,w,*,block_size):
   self.assertIs(a,embed);self.assertEqual(qp.tolist(),[2,3,4,5]);self.assertIs(cp,pos)
   self.assertEqual(set(w),{f'layers.{i}.{n}' for i in range(5) for n in backbone.LAYER_SHAPES}|{'norm.weight'});events.append('body');return hidden
  sentinel=object()
  def propose(a,anchors,head,w,**opts):
   self.assertIs(a,hidden);self.assertEqual(anchors.tolist(),[9]);self.assertEqual(set(w),set(proposal.SELECTOR_KEYS));events.append('proposal');return sentinel
  with patch.object(context_kv,'prepare_context',context),patch.object(backbone,'query_block',body),patch.object(proposal,'propose_greedy',propose):
   out=r._run(data,x,pos,embed,**kw)
  self.assertIsNotNone(out);self.assertEqual(events,['context','body','proposal']);self.assertIs(out.proposal,sentinel);self.assertEqual(out.embedding_ids,(9,248077,248077,248077))
 def test_empty_context_and_invalid_metadata_and_geometry(self):
  t=self.t;data,x,pos,embed,kw=self.fixture(n=0)
  hidden=t.zeros((4,2560),device='cpu',dtype=t.bfloat16)
  with patch.object(context_kv,'prepare_context',side_effect=AssertionError('empty context must not fabricate features')),patch.object(backbone,'query_block',return_value=hidden) as body,patch.object(proposal,'propose_greedy',return_value=object()):
   r._run(data,x,pos,embed,**kw);body.assert_called_once();self.assertEqual(body.call_args.args[1].tolist(),[0,1,2,3]);self.assertEqual(tuple(body.call_args.args[2].shape),(5,0,8,128))
  for bad in (None,r.TargetEvidence('','r','1'*64,'2'*64,'3'*64),r.TargetEvidence('m','r','bad','2'*64,'3'*64)):
   opts=dict(kw,target=bad)
   with self.assertRaises((TypeError,ValueError)):r._run(data,x,pos,embed,**opts)
  with self.assertRaises(ValueError):r._run(dict(list(data.items())[1:]),x,pos,embed,**kw)
  with self.assertRaises(ValueError):r._run(data,x,t.tensor([5],device='cpu',dtype=t.int64),embed,**kw)
if __name__=='__main__':
 if '--run-cpu' in sys.argv:sys.argv.remove('--run-cpu');unittest.main(verbosity=2)
 else:print('Passive default; --run-cpu explicitly runs synthetic assembly tests.')

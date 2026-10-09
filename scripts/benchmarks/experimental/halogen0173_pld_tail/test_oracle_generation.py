"""CPU-only checks for causal-frontier oracle reconstruction, not a model test."""
import unittest
from generate_readylist_oracle import next_committed, prepare_rows, RUNTIME

def row(total,suffix,source='neural',offer=()):
    return dict(session_nonce='s',owner_birth=1,slot_cookie=1,slot_epoch=1,
        context_available=True,context_total=total,context_suffix=suffix,
        current_id=suffix[-1],model_position=total-1,source=source,
        offer_total=len(offer),offer_ids=list(offer))

class OracleGeneration(unittest.TestCase):
    def test_follow_committed_output_beyond_a_rejected_stock_tail(self):
        rows=[row(4,[1,2,3,4],'pld',(5,20,21)),row(6,[1,2,3,4,5,6]),row(8,[3,4,5,6,7,8])]
        self.assertEqual(next_committed(rows,0,3),[5,6,7])
        decoded=dict(header=dict(runtime_sha256=RUNTIME),dataset_complete=True,
            summary=dict(gaps=0,dropped_cumulative=0),rows=rows)
        records,_,_=prepare_rows(decoded,set(range(30)))
        self.assertEqual(records[0][8:11],(5,6,7))
    def test_prefix_divergence_is_not_a_future_label(self):
        self.assertIsNone(next_committed([row(4,[1,2,3,4]),row(7,[1,8,3,4,5,6,7])],0,3))
    def test_retired_generation_cannot_supply_labels(self):
        rows=[row(4,[1,2,3,4]),row(7,[1,2,3,4,5,6,7])];rows[1]['slot_epoch']=2
        self.assertIsNone(next_committed(rows,0,3))

if __name__=='__main__':unittest.main()

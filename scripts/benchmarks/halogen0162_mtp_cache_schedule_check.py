"""CPU-only check of the proposed private head cache's positional replay rule.

This checks a synthetic logical prefix, pooled four-row boundaries and carry.
It does not load Halogen, read weights, import an EP, validate numerical head
state, or claim that native FD rows have contiguous ownership. The retained
disassembly supplies the native accepted-prefix replay call, not this fixture.
"""
import json


def rewind_and_append(prefix, position, rows):
    """Synthetic row ledger for a future private cache, never native storage."""
    if type(position) is not int or not 0 <= position <= len(prefix):
        raise ValueError("missing private history prefix")
    if not rows:
        raise ValueError("a full head call requires at least one row")
    return prefix[:position] + tuple(rows)


def pool_and_carry(prefix):
    """Opaque synthetic groups expose a rewind crossing a four-row boundary."""
    complete = len(prefix) - len(prefix) % 4
    pools = tuple(prefix[i:i + 4] for i in range(0, complete, 4))
    return pools, prefix[complete:]


def check():
    scenarios = []
    for phase in range(4):
        for matched_drafts in range(3):
            for cached_first in (False, True):
                base_position = 8 + phase
                committed = tuple(f"bootstrap:{i}" for i in range(base_position))
                private = rewind_and_append((), 0, committed)
                # Bootstrap/replay normally cached the first proposal. A missed
                # first-proposal cache may invoke a scalar head at base-1.
                if not cached_first:
                    private = rewind_and_append(
                        private, base_position - 1, ("first-proposal-input",))
                    committed = private
                # Depth2's positive offset1 writes at base and saves the native
                # carry at this boundary. The private owner retains its own
                # boundary snapshot and never consumes that 768-byte GPU copy.
                private = rewind_and_append(private, base_position,
                                            ("speculative-poison",))
                k = matched_drafts + 1
                accepted_replay = tuple(f"replay:{i}" for i in range(k))
                # Controller 0x173bb5e -> helper 0x17dcc90 -> fullhead:
                # position = new_target_position-k = base, count = k.
                new_target_position = base_position + k
                private = rewind_and_append(
                    private, new_target_position - k, accepted_replay)
                expected = committed + accepted_replay
                if private != expected or "speculative-poison" in private:
                    raise AssertionError("speculative suffix survived replay")
                if pool_and_carry(private) != pool_and_carry(expected):
                    raise AssertionError("pool boundary or carry survived rewind")
                pools, carry = pool_and_carry(private)
                if len(private) != new_target_position:
                    raise AssertionError("cache length differs from target position")
                scenarios.append(dict(base_position=base_position,
                                      matched_drafts=matched_drafts, k=k,
                                      cached_first=cached_first,
                                      replay_position=base_position,
                                      private_prefix_length=len(private),
                                      complete_pool_rows=len(pools),
                                      carry_rows=len(carry)))
    try:
        rewind_and_append(("one",), 2, ("gap",))
    except ValueError:
        gap_rejected = True
    else:
        raise AssertionError("unknown prefix was accepted")
    return dict(schema=1, passed=True, scenarios_checked=len(scenarios),
                gap_rejected=gap_rejected, scenarios=scenarios,
                qualification="synthetic positional cache schedule only; no native/NPU state or execution",
                native_replay=dict(controller_call_rva="0x173bb5e",
                                   helper_rva="0x17dcc90",
                                   fullhead_call_rva="0x17dcd4f",
                                   fullhead_return_rva="0x17dcd54",
                                   count="k=matched_drafts+1",
                                   position="new_target_position-k"))


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))

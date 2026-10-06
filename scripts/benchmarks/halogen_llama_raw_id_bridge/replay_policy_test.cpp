#include "replay_policy.h"
#include <iostream>
#include <vector>

int main() {
    using ids = std::vector<std::int32_t>;
    const ids draft3{17739, 68507, 11};
    const ids replay4{17739, 68507, 11, 900};
    const ids consumed_prefix{17739, 68507};
    const ids sole_output{17739};
    const ids wrong_first{7963, 68507, 11};
    const ids wrong_second{17739, 68508, 11};
    const ids draft1{17739};
    const ids empty;
    int failures = 0;
    const auto expect = [&](const char* name, bool actual, bool wanted) {
        if (actual != wanted) {
            std::cerr << name << ": expected " << wanted << ", got " << actual << '\n';
            ++failures;
        }
    };
    const auto eligible = [&](bool append, bool reuse, std::size_t committed,
                              const ids& draft, const ids& replay) {
        return raw_id::replay_append_eligible(append, reuse, committed, draft, replay);
    };

    expect("matched consumed prefix appends all retained output", eligible(true, true, 256, draft3, replay4), true);
    expect("retained prefix may end exactly after consumed inputs", eligible(true, true, 256, draft3, consumed_prefix), true);
    expect("count-three with one retained output rebuilds", eligible(true, true, 256, draft3, sole_output), false);
    expect("case12 opening mismatch rebuilds despite future-label match", eligible(true, false, 256, draft3, sole_output), false);
    expect("opening mismatch independently denies full-prefix reuse", eligible(true, false, 256, draft3, replay4), false);
    expect("first consumed ID mismatch rebuilds", eligible(true, true, 256, draft3, wrong_first), false);
    expect("later consumed ID mismatch rebuilds", eligible(true, true, 256, draft3, wrong_second), false);
    expect("default append policy rebuilds", eligible(false, true, 256, draft3, replay4), false);
    expect("exact window capacity appends", eligible(true, true, 508, draft3, replay4), true);
    expect("window eviction rebuilds", eligible(true, true, 509, draft3, replay4), false);
    expect("no retained output cannot cover consumed inputs", eligible(true, true, 256, draft3, empty), false);
    expect("zero consumed inputs preserve committed logits", eligible(true, true, 512, draft1, empty), true);
    expect("zero consumed inputs can append unrelated authoritative output", eligible(true, true, 256, draft1, replay4), true);
    expect("zero consumed inputs still respect capacity", eligible(true, true, 512, draft1, sole_output), false);
    expect("oversized committed history cannot reuse", eligible(true, true, 513, draft1, empty), false);
    expect("missing pending proposal cannot reuse", eligible(true, true, 256, empty, empty), false);

    if (failures) return 1;
    std::cout << "replay policy cases passed\n";
    return 0;
}

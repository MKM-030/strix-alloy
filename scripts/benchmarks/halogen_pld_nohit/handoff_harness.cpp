#include "native_outcome_handoff.h"

#include <cstdio>
#include <new>
#include <type_traits>

using namespace halogen_nohit;
using namespace halogen_nohit::handoff;

namespace {
int failures = 0;
int checks = 0;
NativeOutcomeHandoff feed;
void drain_preview() { PreviewEvent owned{}; (void)feed.pop_preview(owned); }

void check(bool value, const char* message) {
    ++checks;
    if (!value) { ++failures; std::printf("FAIL: %s\n", message); }
}
template<std::size_t N> std::array<std::uint8_t, N> tag(std::uint64_t value) {
    std::array<std::uint8_t, N> out{};
    for (std::size_t i = 0; i < N; ++i) {
        out[i] = static_cast<std::uint8_t>((value >> ((i % 8) * 8)) + i + 1);
    }
    return out;
}
Qualification qualified() { return {true, true, true, true, true, true}; }

// Independent canonical-history oracle. It retains the whole tiny test history,
// appends every native output, and derives a suffix without feed implementation.
// Its digest is an opaque fixture fingerprint, not a cryptographic qualifier.
struct Oracle {
    std::array<std::int32_t, 1024> history{};
    std::size_t used = 3;
    std::uint64_t position = 41;
    Oracle() { history[0] = 10; history[1] = 11; history[2] = 12; }
    void append(const OutcomeCopy& outcome) {
        for (std::size_t i = 0; i < outcome.count; ++i) { history[used++] = outcome.output_ids[i]; }
        position += outcome.count;
    }
    Frontier frontier(const OwnerIdentity& owner, std::uint64_t sequence) const {
        Frontier f{};
        f.owner = owner;
        f.frontier_id = tag<16>(1000 + sequence);
        f.window_id = tag<16>(2000 + sequence);
        f.prefix_length = used;
        f.target_position = position;
        f.current_id = history[used - 1];
        f.window_count = used < kMaxWindowTokens ? used : kMaxWindowTokens;
        f.window_origin = used - f.window_count;
        for (std::size_t i = 0; i < f.window_count; ++i) {
            f.window_ids[i] = history[used - f.window_count + i];
        }
        std::uint64_t fixture_hash = 1469598103934665603ULL;
        for (std::size_t i = 0; i < used; ++i) {
            fixture_hash = (fixture_hash ^ static_cast<std::uint32_t>(history[i])) * 1099511628211ULL;
        }
        f.full_prefix_fingerprint = tag<32>(fixture_hash);
        return f;
    }
};
SeedCopy seed_copy(const Oracle& oracle) {
    SeedCopy seed{};
    OwnerIdentity owner{};
    owner.seed_id = tag<16>(1);
    owner.birth_nonce = tag<16>(2);
    owner.key_id = tag<16>(3);
    owner.model = tag<32>(4);
    owner.tokenizer = tag<32>(5);
    owner.native_epoch = 17;
    owner.owner_generation = 7;
    owner.model_slot_generation = 9;
    seed.canonical = oracle.frontier(owner, 0);
    seed.first_round_id = tag<16>(3000);
    seed.tokens.id_limit = 512;
    seed.tokens.defined_bits.fill(0xff);
    seed.qualification = qualified();
    return seed;
}
bool start(const SeedCopy& seed) {
    // New test-only object lifetime. Production has no reset or eviction API.
    feed.~NativeOutcomeHandoff();
    ::new (static_cast<void*>(&feed)) NativeOutcomeHandoff();
    return feed.initialize(true, seed) && feed.adopt_round(seed.canonical, qualified());
}
OutcomeCopy outcome(std::uint64_t sequence, std::uint8_t count) {
    OutcomeCopy out{};
    out.from = feed.reservation();
    out.outcome_sequence = sequence;
    out.next_round_id = tag<16>(3000 + sequence);
    out.target_position_after = out.from.frontier.target_position + count;
    out.count = count;
    out.native_matched_count = static_cast<std::uint8_t>(count - 1);
    for (std::size_t i = 0; i < count; ++i) { out.output_ids[i] = static_cast<std::int32_t>(20 + sequence * 4 + i); }
    out.qualification = qualified();
    return out;
}
SealCopy seal_copy(const OutcomeCopy& out, const Oracle& oracle) {
    return {out.from, out.outcome_sequence,
        oracle.frontier(out.from.frontier.owner, out.outcome_sequence), out.count,
        SealDisposition::Continue, qualified()};
}
SavedFrame frame() {
    SavedFrame out{};
    out.gpr.fill(0x1234567890ULL);
    out.gpr[Rbp] = 0x10002000;
    out.gpr[Rsp] = 0x20003000;
    out.rflags = 0x2ed7;
    out.outer_stack.fill(0x7a);
    out.opaque_extended_state.fill(0x9d);
    return out;
}
SeamCapture capture(const Frontier& actual, const SavedFrame& saved) {
    SeamCapture c{};
    c.actual_current = actual;
    c.qualification = qualified();
    c.request_rbp = saved.gpr[Rbp];
    c.original_outer_rsp = saved.gpr[Rsp];
    c.positive_pld_policy = c.no_sampler = c.no_suppression = c.positive_width = true;
    c.sufficient_context = c.no_constraints = true;
    c.opening_gate_eligible = true;
    c.native_allowance = 3;
    return c;
}
void write32(std::uint8_t* out, std::uint32_t value) {
    for (std::size_t i = 0; i < 4; ++i) { out[i] = static_cast<std::uint8_t>(value >> (i * 8)); }
}
void write64(std::uint8_t* out, std::uint64_t value) {
    for (std::size_t i = 0; i < 8; ++i) { out[i] = static_cast<std::uint8_t>(value >> (i * 8)); }
}
template<std::size_t N> void copy_tag(std::uint8_t* out, const std::array<std::uint8_t, N>& value) {
    for (std::size_t i = 0; i < N; ++i) { out[i] = value[i]; }
}
PreparedPacket packet(const RoundReservation& reservation) {
    PreparedPacket p{};
    p.reservation = reservation;
    const auto& f = reservation.frontier;
    auto* bytes = p.authenticated.bytes.data();
    copy_tag(bytes, std::array<std::uint8_t, 8>{'H','G','N','P','L','D','P','1'});
    write32(bytes + 8, 1); write32(bytes + 12, 3);
    copy_tag(bytes + 16, f.owner.key_id); copy_tag(bytes + 32, f.owner.model);
    copy_tag(bytes + 64, f.owner.tokenizer); copy_tag(bytes + 96, f.owner.birth_nonce);
    copy_tag(bytes + 112, reservation.round_id); copy_tag(bytes + 128, f.full_prefix_fingerprint);
    write64(bytes + 160, f.prefix_length); write64(bytes + 168, f.target_position);
    write32(bytes + 176, static_cast<std::uint32_t>(f.current_id));
    write64(bytes + 180, f.window_origin); write32(bytes + 188, static_cast<std::uint32_t>(f.window_count));
    write32(bytes + 192, 30); write32(bytes + 196, 31); write32(bytes + 200, 32);
    p.authenticated.length = kMaxPacketBytes;
    p.authenticated.context_epoch = f.owner.native_epoch;
    p.authenticated.ready = p.authenticated.authentication_qualified = p.authenticated.immutable_owned = true;
    // Synthetic trust assertion only: no HMAC qualification is performed.
    return p;
}
bool same_frame(const SavedFrame& a, const SavedFrame& b) {
    return a.gpr == b.gpr && a.rflags == b.rflags && a.outer_stack == b.outer_stack &&
        a.opaque_extended_state == b.opaque_extended_state;
}
void decline(const SeamCapture& c, const PreparedPacket* p, const char* message) {
    auto saved = frame();
    auto expected = saved;
    expected.gpr[Rax] = expected.gpr[Rbp] + 0x1e8;
    const auto ledger_before = feed.consumed_rounds();
    const auto result = feed.consume_at_seam(c, p, saved);
    check(!result.selected && result.resume_rva == kStockResumeRva && same_frame(saved, expected) &&
        feed.consumed_rounds() == ledger_before, message);
}

void canonical_stock_group() {
    Oracle oracle;
    const auto seed = seed_copy(oracle);
    check(start(seed), "qualified exact seed adopts first reservation");
    auto out = outcome(1, 3);
    check(feed.preview(NestedControllerCopy{out}), "stock nested controller preview accepted with copied frame-specific facts");
    check(feed.status() == Status::Preview && feed.queued() == 0, "preview produces no authoritative event");
    drain_preview();
    oracle.append(out);
    check(feed.seal(seal_copy(out, oracle)), "complete matching native seal advances stock controller output");
    check(feed.reservation().frontier == oracle.frontier(seed.canonical.owner, 1), "frontier equals independent full canonical-history oracle");
    AuthoritativeOutcome event{};
    check(feed.pop_authoritative(event) && event.count == 3 && event.output_ids == out.output_ids &&
        event.native_matched_count == 2 && !event.external.selected && event.external_use == ExternalUse::None,
        "native matched count remains native and all no-custom outputs reach worker");
    check(!feed.pop_authoritative(event), "sealed event is drained once");
    check(feed.adopt_round(feed.reservation().frontier, qualified()), "successor adopts from sealed native current truth");
    out = outcome(2, 1);
    check(feed.preview(ScalarCopy{out}), "scalar count-one copied route accepted");
    drain_preview();
    oracle.append(out);
    check(feed.seal(seal_copy(out, oracle)) && feed.reservation().frontier == oracle.frontier(seed.canonical.owner, 2),
        "scalar stock output advances same exact canonical history");
    check(feed.pop_authoritative(event) && event.route == Route::Scalar && event.count == 1 && !event.external.selected,
        "idle no-proposal worker still receives scalar output");
    check(feed.adopt_round(feed.reservation().frontier, qualified()), "third round adopts");
    out = outcome(3, 4);
    check(feed.preview(OuterPldCopy{out}), "outer shifted four-output block accepted");
    drain_preview();
    oracle.append(out);
    check(feed.seal(seal_copy(out, oracle)) && feed.reservation().frontier == oracle.frontier(seed.canonical.owner, 3),
        "outer native PLD full output block advances without custom selection");
    Oracle rolling;
    rolling.used = 511; rolling.position = 901;
    for (std::size_t i = 0; i < rolling.used; ++i) { rolling.history[i] = static_cast<std::int32_t>(i % 500); }
    const auto rolling_seed = seed_copy(rolling);
    check(start(rolling_seed), "qualified 511-ID suffix seed is copied exactly");
    out = outcome(1, 4); (void)feed.preview(OuterPldCopy{out}); drain_preview(); rolling.append(out);
    check(feed.seal(seal_copy(out, rolling)) && feed.reservation().frontier == rolling.frontier(rolling_seed.canonical.owner, 1) &&
        feed.reservation().frontier.window_origin == 3 && feed.reservation().frontier.window_count == 512,
        "bounded suffix rolls at 512 while full independent canonical history remains exact");
}

void connected_consumer_group() {
    Oracle oracle;
    const auto seed = seed_copy(oracle);
    (void)start(seed);
    auto saved = frame();
    const auto before = saved;
    const auto p = packet(feed.reservation());
    const auto result = feed.consume_at_seam(capture(seed.canonical, saved), &p, saved);
    auto expected = before;
    expected.gpr[Rbx] = 3;
    for (std::size_t i = 0; i < 12; ++i) { expected.outer_stack[kProposalOffset + i] = p.authenticated.bytes[192 + i]; }
    check(result.selected && result.resume_rva == kProposalJoinRva && same_frame(saved, expected) && feed.consumed_rounds() == 1,
        "sealed adapter calls SAME reviewed consume interface and preserves exact bounded writes");
    decline(capture(seed.canonical, frame()), &p, "duplicate seam/reply cannot consume reservation twice");
    auto out = outcome(1, 2);
    out.external_use = ExternalUse::Verified;
    out.output_ids[0] = 30; out.output_ids[1] = 99;
    check(feed.preview(OuterPldCopy{out}), "verified custom native outcome preview copies own authoritative output");
    drain_preview();
    auto tentative = packet(feed.reservation());
    decline(capture(seed.canonical, frame()), &tentative, "preview alone never supplies eligible CallerTruth or packet");
    oracle.append(out);
    check(feed.seal(seal_copy(out, oracle)), "verified proposal outcome seal advances");
    AuthoritativeOutcome event{};
    check(feed.pop_authoritative(event) && event.external.selected && event.external.ids[0] == 30 &&
        event.external.ids[2] == 32 && event.output_ids[1] == 99 && event.native_matched_count == 1,
        "external recorded IDs and complete outcomes remain distinct from native matched count");
    (void)feed.adopt_round(feed.reservation().frontier, qualified());
    decline(capture(feed.reservation().frontier, frame()), &p, "old generation and round packet is immediately declined");
    auto late = packet(feed.reservation());
    decline(capture(feed.reservation().frontier, frame()), &late, "late packet after missed round seam declines without waiting");
    out = outcome(2, 1);
    check(feed.preview(ScalarCopy{out}), "missed packet round still captures stock scalar outcome");
    drain_preview();
    oracle.append(out);
    check(feed.seal(seal_copy(out, oracle)), "missed packet does not lose authoritative advancement");

    (void)start(seed);
    const auto p2 = packet(feed.reservation());
    saved = frame();
    (void)feed.consume_at_seam(capture(seed.canonical, saved), &p2, saved);
    out = outcome(1, 3); out.external_use = ExternalUse::OpeningRejected;
    check(feed.preview(NestedControllerCopy{out}), "opening-rejected custom selection may lead to stock controller outcomes");
    drain_preview();
    Oracle second; second.append(out);
    check(feed.seal(seal_copy(out, second)) && feed.pop_authoritative(event) && event.external.selected &&
        event.external_use == ExternalUse::OpeningRejected && event.native_matched_count == 2,
        "stock native acceptance after rejected opening is never invented custom acceptance");

    (void)start(seed); out = outcome(1, 1);
    check(feed.preview(ScalarCopy{out}), "early-drain round obtains a bounded provisional preview");
    PreviewEvent early{};
    check(feed.pop_preview(early) && early.from == out.from && early.next_round_id == out.next_round_id &&
        early.reserved_generation == out.from.generation + 1 && early.route == Route::Scalar &&
        early.outcome_sequence == out.outcome_sequence && early.output_ids == out.output_ids && !early.external.selected,
        "owned complete preview drains before seal so causal private resolution can start");
    check(!feed.pop_preview(early) && feed.status() == Status::Preview && feed.queued() == 0,
        "preview drain is one-shot and never grants sealed packet eligibility");
    Oracle early_oracle; early_oracle.append(out);
    RoundReservation future{early_oracle.frontier(seed.canonical.owner, 1), out.next_round_id, out.from.generation + 1};
    const auto future_packet = packet(future);
    decline(capture(future.frontier, frame()), &future_packet, "prepared successor after early drain stays ineligible until exact seal");
    check(feed.seal(seal_copy(out, early_oracle)), "draining preview retains owned validation copy for continuing seal");
    (void)start(seed); out = outcome(1, 1); (void)feed.preview(ScalarCopy{out});
    (void)feed.pop_preview(early);
    auto terminal = seal_copy(out, early_oracle); terminal.emitted_count = 0;
    (void)feed.seal(terminal);
    RetirementNotice notice{};
    check(feed.pop_retirement(notice) && notice.last_sealed == out.from && notice.provisional_revoked &&
        notice.revoked_outcome_sequence == 1 && notice.revoked_next_round_id == out.next_round_id &&
        notice.revoked_generation == out.from.generation + 1 && !feed.pop_retirement(notice),
        "partial stop publishes observable one-shot revocation to an already-drained preview owner");
    decline(capture(future.frontier, frame()), &future_packet, "late private completion after revocation cannot select");
}

void retirement_group() {
    Oracle oracle;
    const auto seed = seed_copy(oracle);
    (void)start(seed);
    auto out = outcome(1, 2);
    oracle.append(out);
    check(!feed.seal(seal_copy(out, oracle)) && feed.status() == Status::Retired, "missing preview seal retires feed");
    (void)start(seed); out = outcome(1, 2);
    (void)feed.preview(OuterPldCopy{out});
    check(!feed.preview(OuterPldCopy{out}) && feed.status() == Status::Retired, "duplicate preview retires instead of overwriting pending output");
    (void)start(seed); out = outcome(2, 2);
    check(!feed.preview(OuterPldCopy{out}) && feed.status() == Status::Retired, "out-of-order outcome sequence retires");
    (void)start(seed); out = outcome(1, 2); (void)feed.preview(OuterPldCopy{out});
    Oracle complete; complete.append(out);
    auto s = seal_copy(out, complete); s.emitted_count = 1;
    check(!feed.seal(s) && feed.status() == Status::Retired && feed.queued() == 0, "partial stop cannot seal full preview");
    (void)start(seed); out = outcome(1, 2); (void)feed.preview(OuterPldCopy{out});
    s = seal_copy(out, complete); s.disposition = SealDisposition::Retire;
    check(!feed.seal(s) && feed.status() == Status::Retired, "terminal output seal retires private work");
    (void)start(seed); out = outcome(1, 2); (void)feed.preview(OuterPldCopy{out});
    s = seal_copy(out, complete); ++s.outcome_sequence;
    check(!feed.seal(s) && feed.status() == Status::Retired, "wrong seal sequence retires");
    (void)start(seed); out = outcome(1, 2); (void)feed.preview(OuterPldCopy{out});
    s = seal_copy(out, complete); s.actual_next.window_ids[0] ^= 1;
    check(!feed.seal(s) && feed.status() == Status::Retired, "exact full copied window mismatch retires");
    (void)start(seed); out = outcome(1, 2); (void)feed.preview(OuterPldCopy{out});
    s = seal_copy(out, complete); ++s.actual_next.owner.native_epoch;
    check(!feed.seal(s) && feed.status() == Status::Retired, "epoch/address reuse cannot preserve old owner identity");
    (void)start(seed); out = outcome(1, 2); (void)feed.preview(OuterPldCopy{out});
    s = seal_copy(out, complete); (void)feed.seal(s);
    check(!feed.seal(s) && feed.status() == Status::Retired, "duplicate seal retires instead of second advancement");
    check(!feed.initialize(true, seed), "retired instance cannot silently reset nonce/ledger");
}

void qualification_and_budget_group() {
    Oracle oracle;
    auto seed = seed_copy(oracle);
    feed.~NativeOutcomeHandoff(); ::new (static_cast<void*>(&feed)) NativeOutcomeHandoff();
    check(!feed.initialize(false, seed) && feed.status() == Status::Disabled, "handoff defaults off");
    seed.tokens.defined_bits[12 / 8] &= static_cast<std::uint8_t>(~(1U << (12 % 8)));
    check(!start(seed), "undefined seed tail cannot initialize native truth");
    seed = seed_copy(oracle);
    (void)start(seed);
    auto p = packet(feed.reservation());
    auto c = capture(seed.canonical, frame()); c.qualification.native_capture = false;
    decline(c, &p, "caller boolean absence never creates native capture truth");
    (void)start(seed); c = capture(seed.canonical, frame()); c.qualification.reset_excluded = false;
    decline(c, &p, "unknown reset exclusion declines stock identically");
    (void)start(seed); c = capture(seed.canonical, frame()); c.opening_gate_eligible = false;
    decline(c, &p, "native opening-gate ineligibility declines without retiring canonical history");
    auto gate_out = outcome(1, 1); Oracle gate_oracle; gate_oracle.append(gate_out);
    check(feed.status() == Status::Active && feed.preview(ScalarCopy{gate_out}) && feed.seal(seal_copy(gate_out, gate_oracle)),
        "opening-gate decline still advances continuing stock scalar outcome");
    (void)start(seed); c = capture(seed.canonical, frame()); c.actual_current.owner.owner_generation++;
    decline(c, &p, "same saved address with changed owner generation retires or declines");
    (void)start(seed); p = packet(feed.reservation()); p.reservation.frontier.window_id = tag<16>(9999);
    decline(capture(seed.canonical, frame()), &p, "complete envelope window identity is required beyond wire fields");
    (void)start(seed); auto out = outcome(1, 2); out.output_ids[1] = 512;
    check(!feed.preview(OuterPldCopy{out}) && feed.status() == Status::Retired, "undefined last authoritative output retires before event publication");
    (void)start(seed); out = outcome(1, 2); out.native_matched_count = 2;
    check(!feed.preview(OuterPldCopy{out}), "native matched count must describe shifted output count minus one");
    (void)start(seed); out = outcome(1, 2);
    check(!feed.preview(ScalarCopy{out}), "scalar ABI cannot accept outer/controller multi-ID facts");
    (void)start(seed); out = outcome(1, 1); out.next_round_id = feed.reservation().round_id;
    check(!feed.preview(ScalarCopy{out}), "round ID reuse retires without reservation eviction");
    (void)start(seed);
    bool all = true;
    for (std::uint64_t sequence = 1; sequence <= kEventBudget; ++sequence) {
        out = outcome(sequence, 1);
        all = feed.preview(ScalarCopy{out}) && all;
        drain_preview();
        oracle.append(out);
        all = feed.seal(seal_copy(out, oracle)) && all;
        if (sequence < kEventBudget) { all = feed.adopt_round(feed.reservation().frontier, qualified()) && all; }
    }
    check(all && feed.queued() == kEventBudget, "fixed event budget keeps every ordered stock outcome without overwriting");
    (void)feed.adopt_round(feed.reservation().frontier, qualified());
    const auto budget_packet = packet(feed.reservation());
    decline(capture(feed.reservation().frontier, frame()), &budget_packet,
        "stock64 exhausts outcome capacity before packet65 can mutate proposal bytes or consumer ledger");
    out = outcome(kEventBudget + 1, 1);
    check(!feed.preview(ScalarCopy{out}) && feed.status() == Status::Retired && feed.queued() == kEventBudget,
        "exhausted event/round budget retires while preserving unread owned outcomes");
    AuthoritativeOutcome event{}; std::uint64_t sequence = 1;
    while (feed.pop_authoritative(event)) {
        check(event.outcome_sequence == sequence++, "retirement preserves earlier sealed events in exact order");
    }
}
} // namespace

int main() {
    static_assert(std::is_trivially_copyable_v<OuterPldCopy>);
    static_assert(std::is_trivially_copyable_v<NestedControllerCopy>);
    static_assert(std::is_trivially_copyable_v<ScalarCopy>);
    canonical_stock_group(); connected_consumer_group(); retirement_group(); qualification_and_budget_group();
    std::printf("four handoff groups: %s (%d failed checks, %d checks)\n", failures ? "FAIL" : "PASS", failures, checks);
    return failures ? 1 : 0;
}

/* Link this fixture with oracle_relay.S and test_oracle_relay.S only.
 * Its fake helper isolates relay preservation from packet/core behavior.
 */
#include "stream_consumer.h"
#include <assert.h>

__attribute__((visibility("hidden"))) uintptr_t hgn0203_stream_native_fallback;
__attribute__((visibility("hidden"))) uintptr_t hgn0203_stream_native_consume;
__attribute__((visibility("hidden"))) unsigned hgn_fixture_mode;
__attribute__((visibility("hidden"))) unsigned hgn_fixture_path;
__attribute__((visibility("hidden"))) uint8_t hgn_fixture_speculative[0x500];
static uint8_t *expected_frame;
static struct hgn0203_stream_snapshot helper_snapshot;

extern int hgn_fixture_run(unsigned candidate);
extern void hgn_fixture_fallback(void);
extern void hgn_fixture_consume(void);

void hgn_fixture_prepare_frame(uint8_t *frame)
{
    expected_frame = frame;
    for (unsigned i = 0; i < 0x508; ++i) frame[i] = 0x5a;
}

int hgn0203_stream_consume_snapshot(const struct hgn0203_stream_snapshot *saved)
{
    volatile uint8_t *out = (volatile uint8_t *)&helper_snapshot;
    const volatile uint8_t *in = (const volatile uint8_t *)saved;
    for (unsigned i = 0; i < sizeof(helper_snapshot); ++i) out[i] = in[i];
    assert((const uint8_t *)saved + 256 == expected_frame);
    if (!hgn_fixture_mode) return -1;
    int32_t *proposal = (int32_t *)(expected_frame + 0x2a0);
    proposal[0] = 11;
    proposal[1] = 22;
    proposal[2] = 33;
    *(int64_t *)(expected_frame + 0x480) = -1;
    expected_frame[0x220] = 0;
    expected_frame[0xa0] = 0;
    return 3;
}

int hgn_fixture_verify(const struct hgn0203_stream_snapshot *observed, uint8_t *frame)
{
    assert(frame == expected_frame && (uintptr_t)frame % 16 == 0);
    assert(hgn_fixture_path == hgn_fixture_mode);
    const uint64_t expected[15] = {
        0x101, 0x202, 0x303, 0x404, 3, 0x606, 0x707,
        0x808, 0x909, 0xa0a, 0xb0b, 0xc0c,
        (uintptr_t)hgn_fixture_speculative, 0xe0e, 0xf0f
    };
    const uint64_t *actual = (const uint64_t *)observed;
    const uint64_t *before = (const uint64_t *)&helper_snapshot;
    for (unsigned i = 0; i < 15; ++i) {
        assert(before[i] == expected[i]);
        uint64_t value = expected[i];
        if (hgn_fixture_mode && i == 0) value = 3;
        if (!hgn_fixture_mode && i == 5) value = (uintptr_t)hgn_fixture_speculative + 0x268;
        assert(actual[i] == value);
    }
    assert((helper_snapshot.rflags & 0xcd5) == 0x44);
    assert((observed->rflags & 0xcd5) == 0x44);
    for (unsigned i = 0; i < 128; ++i) assert(frame[(int)i - 128] == 0x6b);
    for (unsigned i = 0; i < 0x508; ++i) {
        uint8_t value = 0x5a;
        if (hgn_fixture_mode) {
            if (i >= 0x2a0 && i < 0x2ac) {
                static const uint8_t ids[12] = {11,0,0,0,22,0,0,0,33,0,0,0};
                value = ids[i - 0x2a0];
            }
            if (i >= 0x480 && i < 0x488) value = 0xff;
            if (i == 0xa0 || i == 0x220) value = 0;
        }
        assert(frame[i] == value);
    }
    return 1;
}

int main(void)
{
    hgn0203_stream_native_fallback = (uintptr_t)hgn_fixture_fallback;
    hgn0203_stream_native_consume = (uintptr_t)hgn_fixture_consume;
    assert(hgn_fixture_run(0) == 1);
    assert(hgn_fixture_run(1) == 1);
    return 0;
}

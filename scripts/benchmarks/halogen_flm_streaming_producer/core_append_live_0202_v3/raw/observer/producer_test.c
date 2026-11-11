#include <assert.h>
#include <stdio.h>
#include <string.h>
#define HGN_OBSERVER_CPU_TEST 1
#include "observer.c"

static h_i64 fixture_native;
static unsigned calls, reads, writes, fail_raw, arm_ready, faults;
static unsigned created[4];
static h_u64 tick;
static char arm_text[18];
static unsigned char journals[4][sizeof(struct capture)];

static h_i64 fixture_clock(void) {
  ++calls;
  return fixture_native;
}

h_i64 hgn_cpu_syscall(h_i64 n, h_i64 a, h_i64 b, h_i64 c,
                     h_i64 d, h_i64 ee, h_i64 f) {
  (void)d;
  (void)ee;
  (void)f;
  if (n == 228) {
    struct h_timespec *ts = (struct h_timespec *)b;
    ++reads;
    if (fail_raw)
      return -5;
    tick += 100;
    ts->seconds = 0;
    ts->nanos = (long)tick;
    return 0;
  }
  if (n == 186)
    return 91;
  if (n == 257) {
    const char *path = (const char *)b;
    size_t size = strlen(path);
    if (!strcmp(path, arm_path))
      return arm_ready ? 17 : -2;
    if (strstr(path, "-fault.bin")) {
      ++faults;
      return 80;
    }
    assert(size > 6 && path[size - 6] == '-');
    {
      unsigned index = (unsigned)(path[size - 5] - '0');
      assert(index < 4 && !created[index]);
      assert(!strcmp(path + size - 4, ".bin"));
      created[index] = 1;
      return 30 + index;
    }
  }
  if (n == 5) {
    struct h_stat *st = (struct h_stat *)b;
    memset(st, 0, sizeof(*st));
    st->dev = 9;
    st->ino = a == 17 ? 22 : 100 + (h_u64)a;
    st->mode = 0x8000;
    st->nlink = 1;
    st->size = a == 17 ? 17 : 0;
    return 0;
  }
  if (n == 0) {
    assert(a == 17 && c == 17);
    memcpy((void *)b, arm_text, 17);
    return 17;
  }
  if (n == 1) {
    assert(ordinal < 4 && a == journal_fd[ordinal]);
    assert(buffers[ordinal].done && c == (h_i64)sizeof(struct capture));
    assert(reads % 8 == 0);
    ++writes;
    memcpy(journals[ordinal], (const void *)b, (size_t)c);
    return c;
  }
  if (n == 3)
    return 0;
  assert(!"unexpected syscall or fatal observer failure");
  return -1;
}

static void reset(void) {
  unsigned i;
  memset(buffers, 0, sizeof(buffers));
  memset(journals, 0, sizeof(journals));
  memset(created, 0, sizeof(created));
  memset(in_flight, 0, sizeof(in_flight));
  memset(journal_device, 0, sizeof(journal_device));
  memset(journal_inode, 0, sizeof(journal_inode));
  for (i = 0; i < 4; ++i) {
    buffers[i].magic = 0x3357415231393048ULL;
    buffers[i].version = 3;
    buffers[i].ordinal = i;
    buffers[i].cohort_count = 4;
    buffers[i].epoch_nonce = 1;
    journal_fd[i] = 30 + i;
  }
  active = 1;
  lock_word = selected = ordinal = 0;
  selected_id = 0;
  epoch_nonce = 1;
  consumed_epoch = 0;
  arm_device = 9;
  arm_inode = 22;
  arm_path = "/synthetic/arm";
  journal_prefix = "/synthetic/capture";
  prefix_len = (unsigned)strlen(journal_prefix);
  real_clock = fixture_clock;
  engine_base = 0;
  calls = reads = writes = fail_raw = faults = 0;
  arm_ready = 1;
  memcpy(arm_text, "0000000000000001\n", 18);
  tick = 100;
  fixture_native = 0;
}

static void call(h_u64 pc, void *stack, h_u64 r14, h_u64 rbx,
                 h_i64 r15, h_i64 native) {
  unsigned previous = calls;
  fixture_native = native;
  assert(hgn_phase_now(pc, (h_u64)stack, r14, rbx, r15) == native);
  assert(calls == previous + 1);
}

static void run_epoch(h_u64 nonce, h_u64 first_id) {
  h_u64 pf[180] = {0}, req[180] = {0}, stack[16] = {0};
  const h_u32 outputs[4] = {2, 37, 128, 260};
  unsigned i, initial_writes = writes;
  for (i = 0; i < 4; ++i) {
    h_i64 base = (h_i64)(10000 * (first_id + i));
    double milliseconds = 0.001;
    pf[0] = req[0] = first_id + i;
    *(int *)((h_u8 *)pf + 0x8) = *(int *)((h_u8 *)req + 0x8) = (int)(i % 2);
    *(h_u32 *)((h_u8 *)pf + 0x5c) = 8192 + i;
    *(h_u32 *)((h_u8 *)req + 0x5c) = 8192 + i;
    call(HGN_PF_BEGIN_PC, stack, 1, 23, (h_i64)pf, base + 1000);
    assert(buffers[i].events[0].object == (h_u64)pf);
    *(h_i64 *)((h_u8 *)stack + 0x18) = base + 1000;
    call(HGN_PF_END_PC, stack, 1, 24, (h_i64)pf, base + 2000);
    assert(writes == initial_writes + i);
    *(h_u32 *)((h_u8 *)req + 0x60) = 1;
    memcpy((h_u8 *)req + 0x288, &milliseconds, 8);
    call(HGN_DECODE_BEGIN_PC, stack, (h_u64)req, 25, 1, base + 3000);
    assert(writes == initial_writes + i);
    *(h_i64 *)((h_u8 *)req + 0x290) = base + 3000;
    *(h_u32 *)((h_u8 *)req + 0x60) = outputs[i];
    call(HGN_DECODE_END_PC, stack, (h_u64)req, base + 3000, 1, base + 5000);
    assert(writes == initial_writes + i + 1 && ordinal == i + 1 && !selected);
    assert(buffers[i].count == 4 && buffers[i].done && !buffers[i].overflow);
    assert(buffers[i].epoch_nonce == nonce);
    assert(!buffers[i].events[3].status);
    assert(buffers[i].events[3].native == base + 5000);
    assert(buffers[i].events[3].native_slot == (h_i64)(i % 2));
    assert(buffers[i].events[3].generated == outputs[i]);
  }
  assert(active == 2 && consumed_epoch == nonce);
}

int main(void) {
  h_u64 pf[180] = {0}, stack[16] = {0}, nonce;
  struct h_stat st;
  pf[0] = 17;
  reset();
  active = 2;
  arm_ready = 0;
  call(HGN_PF_BEGIN_PC, 0, 1, 1, 1, -123);
  assert(!reads && !selected);
  arm_ready = 1;
  run_epoch(1, 17);
  assert(calls == 17 && reads == 32 && writes == 4 && !faults);
  call(HGN_PF_BEGIN_PC, 0, 1, 1, 1, -999);
  assert(reads == 32 && writes == 4 && faults == 1);
  arm_ready = 0;
  call(HGN_PF_BEGIN_PC, 0, 1, 1, 1, -998);
  assert(reads == 32 && faults == 1);
  arm_ready = 1;
  memset(created, 0, sizeof(created));
  memcpy(arm_text, "0000000000000002\n", 18);
  run_epoch(2, 100);
  assert(reads == 64 && writes == 8);

  reset();
  active = 0;
  call(HGN_PF_BEGIN_PC, 0, 1, 1, 1, -123);
  assert(!reads);
  reset();
  call(0x999, 0, 1, 1, 1, -456);
  assert(!reads);
  reset();
  *(h_u32 *)((h_u8 *)pf + 0x5c) = 2;
  call(HGN_PF_BEGIN_PC, stack, 1, 1, (h_i64)pf, 123);
  assert(reads == 2 && selected && buffers[0].events[0].prompt == 2);
  reset();
  selected = 1;
  selected_id = 99;
  call(HGN_PF_BEGIN_PC, stack, 1, 1, (h_i64)pf, 123);
  assert(!reads && buffers[0].overflow == HGN_FLAG_INTERFERENCE);
  reset();
  call(HGN_PF_END_PC, stack, 1, 1, (h_i64)pf, 123);
  assert(!reads && !selected && buffers[0].overflow == HGN_FLAG_INTERFERENCE);
  reset();
  *(int *)((h_u8 *)pf + 0x8) = 2;
  call(HGN_PF_BEGIN_PC, stack, 1, 1, (h_i64)pf, 123);
  assert(buffers[0].events[0].status == 4);
  *(int *)((h_u8 *)pf + 0x8) = 0;
  reset();
  fail_raw = 1;
  call(HGN_PF_BEGIN_PC, stack, 1, 1, (h_i64)pf, -789);
  assert(buffers[0].events[0].status == 1);
  assert(buffers[0].events[0].native == -789);
  reset();
  arm_ready = 0;
  assert(load_arm(&nonce, &st) == 0);
  arm_ready = 1;
  arm_text[0] = 'A';
  assert(load_arm(&nonce, &st) == -1);
  memcpy(arm_text, "0000000000000000\n", 18);
  assert(load_arm(&nonce, &st) == -1);
  return 0;
}

/* Side observer: original chrono is called exactly once, original RAX returned.
 * No clock substitution, native stores, accelerator API, allocation, or patch.
 */
#include "capture_core.h"
#include "pins.h"
typedef h_u64 h_uptr;
typedef h_i64 (*h_clock_fn)(void);
struct h_timespec {
  long seconds, nanos;
};
struct h_stat {
  h_u64 dev, ino, nlink;
  h_u32 mode, uid, gid, pad;
  h_u64 rdev;
  h_i64 size, blksize, blocks, atime, atime_ns, mtime, mtime_ns, ctime,
      ctime_ns, reserved[3];
};
struct h_phdr {
  h_u32 type, flags;
  h_u64 offset, vaddr, paddr, filesz, memsz, align;
};
struct h_dl_phdr_info {
  h_uptr base;
  const char *name;
  const struct h_phdr *phdr;
  unsigned short phnum;
};
struct h_dl_info {
  const char *filename;
  void *base;
  const char *symbol;
  void *address;
};
extern void *dlvsym(void *, const char *, const char *);
extern int dladdr(const void *, struct h_dl_info *);
extern int dl_iterate_phdr(int (*)(struct h_dl_phdr_info *, unsigned long,
                                   void *),
                           void *);
extern char *getenv(const char *);
#ifndef HGN_OBSERVER_CPU_TEST
_Static_assert(sizeof(long) == 8 && sizeof(void *) == 8 && sizeof(int) == 4,
               "Linux x86-64 LP64 only");
_Static_assert(sizeof(struct h_stat) == 144, "Linux x86-64 fstat ABI");
#endif

static h_clock_fn real_clock;
static h_uptr engine_base;
static unsigned active, lock_word, selected;
static h_i64 selected_id;
#define HGN_COHORT_COUNT 4
static h_u64 journal_device[HGN_COHORT_COUNT], journal_inode[HGN_COHORT_COUNT];
static h_i64 journal_fd[HGN_COHORT_COUNT] = {-1, -1, -1, -1};
static unsigned in_flight[HGN_COHORT_COUNT];
static unsigned ordinal;
static const char *arm_path;
static const char *journal_prefix;
static unsigned prefix_len;
static h_u64 epoch_nonce, consumed_epoch, arm_device, arm_inode;
static struct capture buffers[HGN_COHORT_COUNT];
static inline h_i64 h_syscall(h_i64 n, h_i64 a, h_i64 b, h_i64 c, h_i64 d,
                              h_i64 e, h_i64 f) {
#ifdef HGN_OBSERVER_CPU_TEST
  extern h_i64 hgn_cpu_syscall(h_i64, h_i64, h_i64, h_i64, h_i64, h_i64, h_i64);
  return hgn_cpu_syscall(n, a, b, c, d, e, f);
#else
  register long r10 __asm__("r10") = d, r8 __asm__("r8") = e,
                    r9 __asm__("r9") = f;
  long result;
  __asm__ volatile("syscall"
                   : "=a"(result)
                   : "a"(n), "D"(a), "S"(b), "d"(c), "r"(r10), "r"(r8), "r"(r9)
                   : "rcx", "r11", "memory");
  return result;
#endif
}
static inline unsigned h_strlen(const char *p) {
  unsigned n = 0;
  while (p[n] && n < 4096)
    ++n;
  return n;
}
static inline int h_equal(const h_u8 *a, const h_u8 *b, unsigned n) {
  unsigned i;
  for (i = 0; i < n; ++i)
    if (a[i] != b[i])
      return 0;
  return 1;
}
static void h_lock(void) {
  while (__atomic_exchange_n(&lock_word, 1, __ATOMIC_ACQUIRE))
    __asm__ volatile("pause");
}
static void h_unlock(void) {
  __atomic_store_n(&lock_word, 0, __ATOMIC_RELEASE);
}
static inline void h_fatal(const char *message) {
  (void)h_syscall(1, 2, (h_i64)message, h_strlen(message), 0, 0, 0);
  (void)h_syscall(231, 125, 0, 0, 0, 0, 0);
  __builtin_unreachable();
}
static inline int h_hash_file(const char *path, const h_u8 *expected,
                              h_u64 expected_size) {
  h_u8 buffer[8192], digest[32];
  struct hgn_sha256 s;
  long fd, n;
  h_u64 size = 0;
  fd = h_syscall(257, -100, (h_i64)path, 0x80000, 0, 0, 0);
  if (fd < 0)
    return 0;
  hgn_sha_init(&s);
  for (;;) {
    n = h_syscall(0, fd, (h_i64)buffer, sizeof(buffer), 0, 0, 0);
    if (n == -4)
      continue;
    if (n < 0) {
      (void)h_syscall(3, fd, 0, 0, 0, 0, 0);
      return 0;
    }
    if (!n)
      break;
    size += (h_u64)n;
    if (size > expected_size) {
      (void)h_syscall(3, fd, 0, 0, 0, 0, 0);
      return 0;
    }
    hgn_sha_update(&s, buffer, (h_u64)n);
  }
  (void)h_syscall(3, fd, 0, 0, 0, 0, 0);
  hgn_sha_final(&s, digest);
  return size == expected_size && h_equal(digest, expected, 32);
}
static inline int h_find_main(struct h_dl_phdr_info *info, unsigned long size,
                              void *unused) {
  unsigned i, j;
  (void)unused;
  if (size < sizeof(*info) || !info->name || info->name[0])
    return 0;
  if (!info->phdr || info->phnum > 64)
    return 1;
  for (i = 0; i < HGN_PIN_COUNT; ++i) {
    int mapped = 0;
    for (j = 0; j < info->phnum; ++j) {
      const struct h_phdr *p = &info->phdr[j];
      if (p->type == 1 && p->flags == 5 && hgn_pins[i].rva >= p->vaddr &&
          hgn_pins[i].rva + hgn_pins[i].size <= p->vaddr + p->memsz)
        mapped = 1;
    }
    if (!mapped || !h_equal((const h_u8 *)(info->base + hgn_pins[i].rva),
                            hgn_pins[i].bytes, hgn_pins[i].size))
      return 1;
  }
  engine_base = info->base;
  return 1;
}
static int h_raw(h_u64 *v) {
  struct h_timespec ts;
  if (h_syscall(228, 4, (h_i64)&ts, 0, 0, 0, 0) < 0 || ts.seconds < 0 ||
      ts.nanos < 0 || ts.nanos >= 1000000000L)
    return 0;
  if ((h_u64)ts.seconds >
      (0x7fffffffffffffffULL - (h_u64)ts.nanos) / 1000000000ULL)
    return 0;
  *v = (h_u64)ts.seconds * 1000000000ULL + (h_u64)ts.nanos;
  return 1;
}

static h_i64 forward(void) {
  if (real_clock)
    return real_clock();
#ifndef HGN_OBSERVER_CPU_TEST
  real_clock = (h_clock_fn)dlvsym(
      (void *)-1L, "_ZNSt6chrono3_V212steady_clock3nowEv", "GLIBCXX_3.4.19");
  if (!real_clock)
    h_fatal("observer: real chrono unavailable\n");
  return real_clock();
#else
  return 0;
#endif
}
static int load_arm(h_u64 *nonce, struct h_stat *st) {
  char text[17];
  h_i64 fd, n;
  unsigned i;
  h_u64 value = 0;
  fd = h_syscall(257, -100, (h_i64)arm_path, 0xa0800, 0, 0, 0);
  if (fd < 0)
    return fd == -2 ? 0 : -1;
  n = h_syscall(5, fd, (h_i64)st, 0, 0, 0, 0);
  if (n < 0 || (st->mode & 0xf000) != 0x8000 || st->size != 17 || st->nlink != 1) {
    (void)h_syscall(3, fd, 0, 0, 0, 0, 0);
    return -1;
  }
  do {
    n = h_syscall(0, fd, (h_i64)text, 17, 0, 0, 0);
  } while (n == -4);
  (void)h_syscall(3, fd, 0, 0, 0, 0, 0);
  if (n != 17 || text[16] != '\n')
    return -1;
  for (i = 0; i < 16; ++i) {
    unsigned digit;
    if (text[i] >= '0' && text[i] <= '9')
      digit = (unsigned)(text[i] - '0');
    else if (text[i] >= 'a' && text[i] <= 'f')
      digit = (unsigned)(text[i] - 'a' + 10);
    else
      return -1;
    value = (value << 4) | digit;
  }
  if (!value)
    return -1;
  *nonce = value;
  return 1;
}
static void epoch_path(char *path, h_u64 nonce, unsigned index) {
  static const char hex[] = "0123456789abcdef";
  const char *suffix = index < HGN_COHORT_COUNT ? ".bin" : "fault.bin";
  unsigned i, at = prefix_len;
  for (i = 0; i < prefix_len; ++i)
    path[i] = journal_prefix[i];
  path[at++] = '-';
  for (i = 0; i < 16; ++i)
    path[at++] = hex[(nonce >> ((15 - i) * 4)) & 15];
  path[at++] = '-';
  if (index < HGN_COHORT_COUNT)
    path[at++] = (char)('0' + index);
  for (i = 0; suffix[i]; ++i)
    path[at++] = suffix[i];
  path[at] = 0;
}
static void epoch_fault(h_u64 nonce) {
  char path[4096];
  h_i64 fd;
  epoch_path(path, nonce, HGN_COHORT_COUNT);
  fd = h_syscall(257, -100, (h_i64)path, 0xa04c1, 0600, 0, 0);
  if (fd == -17)
    return;
  if (fd < 0)
    h_fatal("observer: epoch fault marker unavailable\n");
  (void)h_syscall(3, fd, 0, 0, 0, 0, 0);
}
/* Called under the observer lock, before the first RAW bracket of an epoch.
 * Root owns idle-only arm replacement and supplies increasing immutable nonces.
 */
static int prepare_epoch(void) {
  struct h_stat st, js;
  char path[4096];
  h_u64 nonce;
  unsigned i, j;
  int armed = load_arm(&nonce, &st);
  if (!armed)
    return 0;
  if (armed < 0 || nonce < consumed_epoch)
    h_fatal("observer: immutable increasing epoch arm rejected\n");
  if (nonce == consumed_epoch) {
    epoch_fault(nonce);
    return 0;
  }
  for (i = 0; i < HGN_COHORT_COUNT; ++i)
    if (in_flight[i]) {
      epoch_fault(nonce);
      return 0;
    }
  for (i = 0; i < HGN_COHORT_COUNT; ++i) {
    epoch_path(path, nonce, i);
    journal_fd[i] = h_syscall(257, -100, (h_i64)path, 0xa04c1, 0600, 0, 0);
    if (journal_fd[i] < 0)
      h_fatal("observer: fresh epoch journals required\n");
    if (h_syscall(5, journal_fd[i], (h_i64)&js, 0, 0, 0, 0) < 0 ||
        (js.mode & 0xf000) != 0x8000 || js.nlink != 1 || js.size != 0)
      h_fatal("observer: epoch journal stat rejected\n");
    if (js.dev == st.dev && js.ino == st.ino)
      h_fatal("observer: arm journal alias rejected\n");
    for (j = 0; j < i; ++j)
      if (js.dev == journal_device[j] && js.ino == journal_inode[j])
        h_fatal("observer: epoch journal inode aliases rejected\n");
    journal_device[i] = js.dev;
    journal_inode[i] = js.ino;
    buffers[i] = (struct capture){0};
    buffers[i].magic = 0x3357415231393048ULL;
    buffers[i].version = 3;
    buffers[i].ordinal = i;
    buffers[i].cohort_count = HGN_COHORT_COUNT;
    buffers[i].epoch_nonce = nonce;
  }
  epoch_nonce = nonce;
  arm_device = st.dev;
  arm_inode = st.ino;
  ordinal = 0;
  selected_id = 0;
  __atomic_store_n(&selected, 0, __ATOMIC_RELEASE);
  __atomic_store_n(&active, 1, __ATOMIC_RELEASE);
  return 1;
}
static void flush_capture(void) {
  const h_u8 *data = (const h_u8 *)&buffers[ordinal];
  h_u64 left = sizeof(buffers[ordinal]);
  h_i64 n;
  /* This function is reached ONLY after Decode-end RAW-after was captured. */
  while (left) {
    n = h_syscall(1, journal_fd[ordinal], (h_i64)data, (h_i64)left, 0, 0, 0);
    if (n == -4)
      continue;
    if (n <= 0)
      break;
    data += (h_u64)n;
    left -= (h_u64)n;
  }
  (void)h_syscall(3, journal_fd[ordinal], 0, 0, 0, 0, 0);
  journal_fd[ordinal] = -1;
  ++ordinal;
  __atomic_store_n(&selected, 0, __ATOMIC_RELEASE);
  if (ordinal == HGN_COHORT_COUNT) {
    consumed_epoch = epoch_nonce;
    __atomic_store_n(&active, 2, __ATOMIC_RELEASE);
  }
}
#ifndef HGN_OBSERVER_CPU_TEST
__attribute__((constructor)) static void initialize(void) {
  struct h_dl_info provider;
  char path[4096];
  h_i64 n, fd;
  const char *on, *prefix, *base;
  h_u64 raw;
  on = getenv("HGN0202_RAW_ENABLE");
  if (!on || on[0] != '1' || on[1])
    return;
  n = h_syscall(89, (h_i64) "/proc/self/exe", (h_i64)path, sizeof(path) - 1, 0,
                0, 0);
  if (n <= 0 || n >= (h_i64)sizeof(path) - 1)
    h_fatal("observer: executable path unavailable\n");
  path[n] = 0;
  base = path;
  for (n = 0; path[n]; ++n)
    if (path[n] == '/')
      base = path + n + 1;
  /* An enabled preload inherited by helper executables remains passthrough. */
  if (h_strlen(base) != 11 ||
      !h_equal((const h_u8 *)base, (const h_u8 *)"flash_serve", 11))
    return;
  real_clock = (h_clock_fn)dlvsym(
      (void *)-1L, "_ZNSt6chrono3_V212steady_clock3nowEv", "GLIBCXX_3.4.19");
  if (!real_clock)
    h_fatal("observer: real chrono unavailable\n");
  if (!h_hash_file("/proc/self/exe", hgn_engine_sha, HGN_ENGINE_BYTES))
    h_fatal("observer: exact engine rejected\n");
  (void)dl_iterate_phdr(h_find_main, (void *)0);
  if (!engine_base)
    h_fatal("observer: mapped pins rejected\n");
  if (!dladdr((const void *)real_clock, &provider) || !provider.filename ||
      !provider.base ||
      (h_uptr)real_clock - (h_uptr)provider.base != HGN_PROVIDER_RVA ||
      !h_equal((const h_u8 *)real_clock, hgn_provider_code,
               sizeof(hgn_provider_code)) ||
      !h_hash_file(provider.filename, hgn_provider_sha, HGN_PROVIDER_BYTES))
    h_fatal("observer: exact real provider rejected\n");
  if (!h_raw(&raw))
    return;
  prefix = getenv("HGN0202_RAW_JOURNAL_PREFIX");
  if (!prefix || prefix[0] != '/' || (prefix_len = h_strlen(prefix)) > 3970)
    h_fatal("observer: absolute fresh journal prefix required\n");
  journal_prefix = prefix;
  arm_path = getenv("HGN0202_RAW_ARM_FILE");
  if (!arm_path)
    h_fatal("observer: absent explicit arm file required\n");
  {
    if (arm_path[0] != '/' || h_strlen(arm_path) >= 4096)
      h_fatal("observer: absolute absent arm file required\n");
    fd = h_syscall(257, -100, (h_i64)arm_path, 0xa0800, 0, 0, 0);
    if (fd >= 0) {
      (void)h_syscall(3, fd, 0, 0, 0, 0, 0);
      h_fatal("observer: arm file already exists\n");
    }
    if (fd != -2)
      h_fatal("observer: arm path rejected\n");
  }
  __atomic_store_n(&active, 2, __ATOMIC_RELEASE);
}
#endif
__attribute__((visibility("hidden"))) h_i64
hgn_phase_now(h_uptr caller, h_uptr stack, h_uptr r14, h_uptr rbx, h_i64 r15) {
  struct event e = {0};
  h_i64 native;
  unsigned capture_ordinal;
  unsigned enabled = __atomic_load_n(&active, __ATOMIC_ACQUIRE);
  e.site = site(caller - engine_base);
  if (!enabled || !e.site)
    return forward();
  /* Startup generation remains passthrough until the collector creates the
   * explicit arm file. Once armed, every bound endpoint participates in the
   * interference check, including orphan decode or prefill-end events. */
  e.object = select_object(e.site, r14, (h_u64)r15);
  h_lock();
  if (__atomic_load_n(&active, __ATOMIC_ACQUIRE) == 2 && !prepare_epoch()) {
    h_unlock();
    return forward();
  }
  if (ordinal >= HGN_COHORT_COUNT ||
      !__atomic_load_n(&active, __ATOMIC_ACQUIRE)) {
    h_unlock();
    return forward();
  }
  capture_ordinal = ordinal;
  if (!__atomic_load_n(&selected, __ATOMIC_ACQUIRE)) {
    if (e.site != 1) {
      buffers[ordinal].overflow |= HGN_FLAG_INTERFERENCE;
      h_unlock();
      return forward();
    }
    selected_id = *(const h_i64 *)e.object;
    __atomic_store_n(&selected, 1, __ATOMIC_RELEASE);
  }
  if (*(const h_i64 *)e.object != selected_id) {
    buffers[ordinal].overflow |= HGN_FLAG_INTERFERENCE;
    h_unlock();
    return forward();
  }
  if (in_flight[capture_ordinal]++)
    buffers[capture_ordinal].overflow |= HGN_FLAG_INTERFERENCE;
  h_unlock();
  /* Bracket the one real call BEFORE sampling the recorded native fields. */
  if (!h_raw(&e.raw_before))
    e.status |= 1;
  native = forward();
  e.native = native;
  if (!h_raw(&e.raw_after) || !hgn_bracket_valid(e.raw_before, e.raw_after))
    e.status |= 1;
  e.caller_rva = caller - engine_base;
  e.caller_stack = stack;
  e.saved_r14 = r14;
  e.saved_r15 = (h_u64)r15;
  e.saved_rbx = rbx;
  e.object = select_object(e.site, r14, (h_u64)r15);
  e.request_id = *(const h_i64 *)e.object;
  e.native_slot = *(const int *)(e.object + 0x8);
  if (e.request_id <= 0 || e.native_slot < 0 || e.native_slot > 1)
    e.status |= 4;
  e.tid = h_syscall(186, 0, 0, 0, 0, 0, 0);
  e.prompt = *(const h_u32 *)(e.object + 0x5c);
  e.generated = *(const h_u32 *)(e.object + 0x60);
  if (e.site <= 2) {
    e.prefill_accum_bits = *(const h_u64 *)(e.object + 0x528);
    e.native_start = e.site == 1 ? native : *(const h_i64 *)(stack + 0x18);
  } else {
    e.published_prefill_bits = *(const h_u64 *)(e.object + 0x288);
    e.native_start = e.site == 3 ? native : *(const h_i64 *)(e.object + 0x290);
    if (e.site == 4 && (h_i64)rbx != e.native_start)
      e.status |= 2;
  }
  h_lock();
  --in_flight[capture_ordinal];
  if (e.site == 4 && capture_ordinal == HGN_COHORT_COUNT - 1) {
    struct h_stat st;
    h_u64 nonce;
    if (load_arm(&nonce, &st) != 1 || nonce != epoch_nonce ||
        st.dev != arm_device || st.ino != arm_inode) {
      buffers[capture_ordinal].overflow |= HGN_FLAG_INTERFERENCE;
      epoch_fault(epoch_nonce);
    }
  }
  if (ordinal == capture_ordinal && ordinal < HGN_COHORT_COUNT && selected_id == e.request_id &&
      append(&buffers[ordinal], &e))
    flush_capture();
  h_unlock();
  return native;
}

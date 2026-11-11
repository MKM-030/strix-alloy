/* Root-only CPU fixture: reads exact ELF bytes; never loads/executes the ELF. */
#include <assert.h>
#include <elf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cold_addresses.h"
#include "sha256_core.h"

int main(int argc, char **argv) {
    assert(argc == 5); /* ELF path and three independent proof RVAs */
    FILE *file = fopen(argv[1], "rb"); assert(file);
    unsigned char *data = malloc(HGN0202_ENGINE_BYTES); assert(data);
    assert(fread(data, 1, HGN0202_ENGINE_BYTES, file) == HGN0202_ENGINE_BYTES);
    assert(fgetc(file) == EOF); assert(fclose(file) == 0);
    struct hgn_sha256 sha; unsigned char actual[32];
    hgn_sha_init(&sha); hgn_sha_update(&sha, data, (unsigned)HGN0202_ENGINE_BYTES);
    hgn_sha_final(&sha, actual); assert(memcmp(actual, hgn0202_engine_sha, 32) == 0);
    const Elf64_Ehdr *eh = (const Elf64_Ehdr *)data;
    assert(memcmp(eh->e_ident, ELFMAG, SELFMAG) == 0);
    assert(eh->e_ident[EI_CLASS] == ELFCLASS64 && eh->e_phentsize == sizeof(Elf64_Phdr));
    assert(eh->e_phoff + (size_t)eh->e_phnum * sizeof(Elf64_Phdr) <= HGN0202_ENGINE_BYTES);
    const uintptr_t base = (uintptr_t)0x100000000ULL;
    uintptr_t addresses[3];
    assert(hgn0202_cold_addresses(base, &addresses[0], &addresses[1], &addresses[2]));
    for (unsigned i = 0; i < 3; ++i) {
        char *end = NULL; uintptr_t expected = (uintptr_t)strtoull(argv[i + 2], &end, 0);
        assert(end && *end == '\0' && addresses[i] == base + expected);
        assert(hgn0202_pins[i].rva == expected);
        unsigned matched = 0;
        for (unsigned j = 0; j < eh->e_phnum; ++j) {
            const Elf64_Phdr *ph = (const Elf64_Phdr *)(data + eh->e_phoff + j * sizeof(*ph));
            if (ph->p_type != PT_LOAD || !(ph->p_flags & PF_X) || expected < ph->p_vaddr)
                continue;
            uint64_t offset = expected - ph->p_vaddr;
            if (offset + hgn0202_pins[i].bytes > ph->p_filesz) continue;
            assert(ph->p_offset + offset + hgn0202_pins[i].bytes <= HGN0202_ENGINE_BYTES);
            assert(memcmp(data + ph->p_offset + offset, hgn0202_pins[i].original,
                          hgn0202_pins[i].bytes) == 0); ++matched;
        }
        assert(matched == 1);
    }
    assert(!hgn0202_cold_addresses(UINTPTR_MAX, &addresses[0], &addresses[1], &addresses[2]));
    free(data); puts("fresh actual ELF cold address roles PASS; ELF not executed");
    return 0;
}

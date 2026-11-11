#ifndef HGN0202_COLD_ADDRESSES_H
#define HGN0202_COLD_ADDRESSES_H
#include <stdint.h>
#include <stddef.h>
#include "native_pins.h"

/* Validation and actual patch/configuration consume the same generated rows. */
static inline int hgn0202_cold_addresses(uintptr_t base, uintptr_t *seam,
                                       uintptr_t *fallback, uintptr_t *consume) {
    if (!seam || !fallback || !consume || HGN0202_PIN_COUNT != 3 ||
        hgn0202_pins[0].bytes != 7 ||
        hgn0202_pins[1].rva != hgn0202_pins[0].rva + 7 ||
        hgn0202_pins[2].rva <= hgn0202_pins[1].rva ||
        hgn0202_pins[2].rva >= HGN0202_ENGINE_BYTES ||
        base > UINTPTR_MAX - HGN0202_ENGINE_BYTES)
        return 0;
    *seam = base + hgn0202_pins[0].rva;
    *fallback = base + hgn0202_pins[1].rva;
    *consume = base + hgn0202_pins[2].rva;
    return 1;
}
#endif

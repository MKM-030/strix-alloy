/* rand-check.c - verify the RAND_MAX claim the reviewer raised.
 *
 * llama-bench feeds the model with `std::rand() % n_vocab`. If the Windows CRT caps
 * RAND_MAX at 32767, that expression cannot reach token IDs above 32767 in a 248k vocab,
 * so the benchmark never exercises ~87% of the vocabulary -- a comparability defect for
 * an MoE with hashed PLE lookups. This prints the actual values from THIS toolchain.
 */
#include <stdio.h>
#include <stdlib.h>

int main(void) {
    printf("RAND_MAX                  = %d\n", RAND_MAX);
    printf("n_vocab (Qwen3.8-FN)      = %d\n", 248320);

    /* how many distinct IDs can rand()%  248320 possibly produce? */
    int seen_hi = -1;
    for (int i = 0; i < 2000000; ++i) {
        int t = rand() % 248320;
        if (t > seen_hi) seen_hi = t;
    }
    printf("max token id seen in 2e6 draws = %d  (%.1f%% of vocab reachable)\n",
           seen_hi, 100.0 * (seen_hi + 1) / 248320.0);

    /* the same modulo applied to a value that CAN reach the full range */
    int lo = 0, hi = 0;
    for (int i = 0; i < 400000; ++i) {
        int t = rand() % 248320;
        if (t < 32768) lo++; else hi++;
    }
    printf("draws below 32768: %.2f%%   at/above: %.2f%%\n",
           100.0 * lo / 400000.0, 100.0 * hi / 400000.0);
    return 0;
}

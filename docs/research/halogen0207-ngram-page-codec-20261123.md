# Halogen 0.20.7 lossless N-Gram block compression

The best held-out result used independently decodable 16 KiB zlib blocks.
It saved **17.68%** after accounting for the scale and index. The same layout
would touch **4.27** packed 4 KiB pages on average for one isolated block
miss in the model, compared with **1.03** native pages for an isolated
160-byte row with uniformly distributed start offsets.

| Codec | Block | Held-out blocks | Net space saved | Warm decode + CRC median | Modeled packed pages per miss |
| --- | ---: | ---: | ---: | ---: | ---: |
| zlib-6 | 4 KiB | 180 | 16.23% | 13.60 µs | 1.83 |
| zlib-6 | 8 KiB | 80 | 17.17% | 23.75 µs | 2.65 |
| zlib-6 | 16 KiB | 30 | 17.68% | 44.80 µs | 4.27 |
| XZ-1 | 4 KiB | 180 | 11.27% | 136.60 µs | 1.88 |
| XZ-1 | 8 KiB | 80 | 13.49% | 288.45 µs | 2.73 |
| XZ-1 | 16 KiB | 30 | 14.75% | 565.05 µs | 4.40 |

The test used 32 sealed, detached FP8 samples from
`layers.1.ple.ngram_embedding.weight`. It selected only fully captured
blocks aligned to their offsets in the standalone HGN file. Every block
reconstructed byte for byte. The size estimate includes offsets,
checksums, raw-block flags, a small header and the FP8 scale. Warm timings
include Python call overhead, codec decoding and CRC verification. The
read model assumes a resident index and no reuse between misses. It
excludes filesystem allocation, readahead and the engine's actual row order.

Every candidate missed the predeclared screen of at least 20% net capacity
savings and fewer pages than a raw isolated read. The managed serving path
continues to use the canonical HGN. The test read only the detached samples
and used no NPU or GPU. SSD throughput and engine token rates are outside its
scope. [Earlier row-based compression screen](halogen-npu-native-route-20261005.md)

The local artifacts are under
`server/.local/halogen-update-20261122/primary0207/ngram-page-codec-prep-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Detached sample manifest | `92bc1e6e4da3cd3bff13ec462e3abab3d209e90fb4eb8491470678487ae4b5e6` |
| Screen implementation | `1cf504ccd46b4d392c5b75e7b93b8dfc21bce4d910d97eb0a332fa124fdf2f8a` |
| Full result | `4ee4b2b1d613c8779ffd4c852a96b12a56a3c72cd27d338552528eb2c2fdc643` |

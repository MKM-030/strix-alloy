# HT decoder attribution

`hgn_ht_slice.py` is a modified decoder-only adaptation of the Apache-2.0
`halogen-v2-tooling/tooling` sources at commit
`6e5c4a2fc2d5c8dec044c30aa1f41b9419972655`:

- `hgnht.py`: SHA256 `6abedcfda20c5f86bc7f5ad3ad3363be84a65e3c0f8b4b658d9e94f64855ec5a`.
- `hgnenc.py`: SHA256 `f9612777daf6d2b26bdf1dd8971e739fd6ddc3bc8ae47a06909f54b7752cee92`.

The original source describes its codebook and packing as recovered from the
0.15.0 gfx1151 decoder. This adaptation retains only the trellis decoder and
normalized Sylvester H128 transform. It adds strict metadata checks, complete
128-row group slicing, a 64-MiB decoded-output limit, bounded binary reads and
per-range/decoded SHA256 receipts. Native encoder, ctypes and file-mapping
helpers are excluded. Synthetic parity does not establish current-engine
numerical equivalence.

The synthetic tests' expected hashes were generated with only decoder function
AST nodes from these pinned sources, without importing their encoder modules.
Both 128-row and 256-row fixtures contain generated nibbles, signs and scales;
they contain no model data.

The upstream distribution contained no separate NOTICE file or source copyright
notice in these two modules. Its complete Apache License 2.0 is preserved in
`hgn_ht_slice.LICENSE`; the repository's root MIT license does not replace it.

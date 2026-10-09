# Historical native HC6 register-remap sources

This is a default-off audit archive for one pinned Halogen 0.17.2 gfx1151 experiment. It does not change normal serving or provide portable startup. The measured decision belongs in [the HC6 report](../../../../docs/research/halogen0172-hc6-register-remap-20261009.md); that report records the complete stock/candidate/stock cohort and rejection for serving adoption.

“Stock” means the unchanged normal project 0.17.2 profile, including existing WSL memory-registration/upload adapters, rather than a vanilla upstream setup. The experimental addition is only the HC6 remap and redirect.

Nine preparation/audit files are copied byte for byte from the private experiment directory. `source-hashes.json` records their original sizes and SHA256 values. The JSON patch records contain metadata and small guarded operand replacements, not the complete kernel. `static-review.json` and `shim-contract.md` are historical preparation records; their source-only wording and review-time pins do not supersede final runtime evidence.

The change reuses dead native registers for six middle-consumer temporaries and lowers whole-kernel VGPR use from 125 to 120, preserving instruction order and arithmetic. Descriptor/metadata rounding implies physical wave32 allocation 144 to 120 and a VGPR-only theoretical limit of 10 to 12 waves/SIMD. No observed occupancy or speedup follows from those limits.

Dependencies remain private or separately installed:

- `audit_hc6_remap.py` and `transform.py` need the omitted hash-pinned native engine, extracted full ELF bundle and retained disassembly. Their default input paths assume the private preparation-directory layout. The transform writes only inside its own artifact directory.
- `redirect.c` targets Linux x86-64 and the pinned installed HIP ABI, dynamically uses HIP/runtime symbols and `libcrypto.so.3`, and checks the exact original engine/code hashes. It redirects only the qualified native descriptor/caller/geometry after all arming variables pass; otherwise it follows stock.
- `build_redirect.py` assumes the original Windows C-drive/`Ubuntu-24.04` WSL user/GCC layout and expects an omitted wrapper and candidate file beside it. Copying it does not supply the sealed controller, launcher, runtime or authentication/profile state needed for serving.
- `analyze_cohort.py` is CPU-only and uses the Python standard library. It needs the complete private retained evidence, both measured client sources and the sibling matching-run stock-before lifecycle receipt. An archived copy must receive `--evidence-dir` pointing to that retained directory; its default archive directory contains no cohort. It performs no inference, networking, HIP or lifecycle action.

Private references include Windows `.local` paths under `C:/Projects/strix-alloy-clean`, the pinned `/usr/local/bin/flash_serve`, container/runtime and WSL identities, and model/checkpoint paths under `/home/revn/halogen-models-native` and `/mnt/c/AI/models`. These dependencies are disclosed, not bundled. No native/candidate binary, `.so`, model/weight/tensor data, raw disassembly, prompt/response, stats binary, credential or live service receipt is included.

The frozen workload uses synthetic repeated 8K input and 128 generated tokens. Acceptance is combined native API MTP+PLD accounting, not isolated native MTP. Output parity on that bounded workload cannot establish general numerical equivalence. Relocating these historical sources does not make the experiment portable or independently reproducible without the omitted inputs.

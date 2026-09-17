per_expert = 2560*640 + 2560*640 + 640*2560
experts = 48 * 512 * per_expert
print(f"expert params       : {experts/1e9:.1f} B")
print(f"  IQ4_NL (4.5 bpw)  : {experts*4.5/8/1e9:.1f} GB   (our census: 67.9 GB of routed experts)")
ple = 160 * 320001536
print(f"PLE table params    : {ple/1e9:.1f} B")
print(f"  IQ4_NL            : {ple*4.5/8/1e9:.1f} GB   (our census: 28.8 GB PLE)")
print()
print(f"transformer-only    : ~{experts/1e9:.0f}B experts + ~4B attn/embd/norms -> ~125B (matches model card)")
print(f"with PLE table      : ~{(experts + 4e9 + ple)/1e9:.0f}B  <- where '177B' likely came from")

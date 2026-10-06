/* Augment GNU ld's shared-library script. Exact object basenames are required.
   Frozen relay input sections are extracted before the default .text/.eh_frame
   rules. No unrelated installer/config-function FDE enters this copied island. */
SECTIONS
{
  .hgn_nohit_rx ALIGN(4096) :
  {
    HIDDEN(__hgn_island_begin = .);
    HIDDEN(__hgn_rx_begin = .);
    KEEP(*native_frame_relay.o(.text))
    KEEP(*native_frame_install_link.o(.text))
    HIDDEN(__hgn_code_end = .);
    . = ALIGN(4096);
    HIDDEN(__hgn_rx_end = .);
  }
  .hgn_nohit_ro ALIGN(4096) :
  {
    HIDDEN(__hgn_ro_begin = .);
    KEEP(*native_frame_relay.o(.rodata))
    . = ALIGN(8);
    HIDDEN(__hgn_frames_begin = .);
    KEEP(*native_frame_relay.o(.eh_frame))
    KEEP(*native_frame_install_link.o(.eh_frame))
    LONG(0)
    HIDDEN(__hgn_frames_end = .);
    . = ALIGN(4096);
    HIDDEN(__hgn_ro_end = .);
  }
  .hgn_nohit_config ALIGN(4096) :
  {
    HIDDEN(__hgn_config_begin = .);
    KEEP(*native_frame_config.o(.data .data.* .bss .bss.*))
    . = ALIGN(4096);
    HIDDEN(__hgn_config_end = .);
  }
  .hgn_nohit_owned ALIGN(4096) :
  {
    HIDDEN(__hgn_owned_begin = .);
    KEEP(*native_frame_install_link.o(.hgn_nohit_observation))
    . = ALIGN(4096);
    HIDDEN(__hgn_owned_end = .);
    HIDDEN(__hgn_island_end = .);
  }
}
INSERT BEFORE .text;
ASSERT(halogen_nohit_native_frame_relay == __hgn_rx_begin, "relay object missing/reordered")
ASSERT(halogen_nohit_frame_observer >= __hgn_rx_begin && halogen_nohit_frame_observer < __hgn_code_end, "observer outside island")
ASSERT(halogen_nohit_native_stock_resume >= __hgn_rx_begin && halogen_nohit_native_stock_resume + 9 <= __hgn_code_end, "stock pad outside island")
ASSERT(halogen_nohit_relay_configuration >= __hgn_config_begin && halogen_nohit_relay_configuration < __hgn_config_end, "configuration outside island")
ASSERT(halogen_nohit_installed_observation == __hgn_owned_begin, "owned observation missing/reordered")
ASSERT(__hgn_rx_end == __hgn_ro_begin && __hgn_ro_end == __hgn_config_begin && __hgn_config_end == __hgn_owned_begin, "island ranges are not contiguous")
/* No copied code may acquire a PLT/GOT dependency through later link changes. */
NOCROSSREFS_TO(.plt .hgn_nohit_rx)
NOCROSSREFS_TO(.plt.got .hgn_nohit_rx)
NOCROSSREFS_TO(.got .hgn_nohit_rx)
NOCROSSREFS_TO(.got.plt .hgn_nohit_rx)
NOCROSSREFS_TO(.text .hgn_nohit_rx)

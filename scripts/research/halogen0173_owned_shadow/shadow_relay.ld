SECTIONS {
  .hgn_shadow_island ALIGN(4096) : {
    hgn_shadow_island_begin = .;
    KEEP(*shadow_relay.o(.hgn_shadow_relay_templates))
    . = ALIGN(8);
    hgn_shadow_island_frames = .;
    KEEP(*shadow_relay.o(.eh_frame))
    LONG(0)
    hgn_shadow_island_frames_end = .;
    hgn_shadow_island_end = .;
  }
}
INSERT AFTER .text;

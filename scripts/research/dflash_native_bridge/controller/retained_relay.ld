SECTIONS {
  .hgn_dflash_island ALIGN(4096) : {
    hgn_dflash_island_begin = .;
    KEEP(*retained_relay_island.o(.hgn_dflash_relay_templates))
    . = ALIGN(8);
    hgn_dflash_island_frames = .;
    KEEP(*retained_relay_island.o(.hgn_dflash_relay_frames))
    LONG(0)
    hgn_dflash_island_frames_end = .;
    hgn_dflash_island_end = .;
  }
}
INSERT AFTER .text;

{ lib, pkgs, ... }:

let
  ciruHostLibraries = with pkgs; [
    stdenv.cc.cc.lib
    zlib
    vulkan-loader
    libdrm
    elfutils
    numactl
    openssl
  ];
in
{
  programs.nix-ld = {
    enable = true;
    libraries = ciruHostLibraries;
  };

  environment.sessionVariables.CIRU_HOST_LIBRARY_PATH =
    lib.makeLibraryPath ciruHostLibraries;
}

{ pkgs ? import <nixpkgs> { } }:

let
  hostLibraries = with pkgs; [
    stdenv.cc.cc.lib
    zlib
    vulkan-loader
    libdrm
    elfutils
    numactl
    openssl
  ];
in
pkgs.mkShell {
  packages = with pkgs; [
    uv
    gcc
    gnumake
    cmake
    ninja
    git
    pkg-config
    unixtools.xxd
    gnutar
    coreutils
    findutils
  ];

  CIRU_HOST_LIBRARY_PATH = pkgs.lib.makeLibraryPath hostLibraries;
}

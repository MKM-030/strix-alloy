@echo off
rem Thin entry point so the launcher can be double-clicked or pinned to the taskbar.
rem It adds no behaviour of its own - every option passes straight through.
rem
rem   "Launch Flash Next.cmd"                                    serial, default port 8899
rem   "Launch Flash Next.cmd" -DraftPath "D:\mtp-sidecar.gguf"   MTP profile
rem   "Launch Flash Next.cmd" -Stop                              stop it again
rem
rem -NoExit keeps the window open so the loading progress and any error stay readable.
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0launch-flash-next.ps1" %*

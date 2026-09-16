@echo off
set OUT=C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\bcd-full.txt
bcdedit /enum all /v > "%OUT%" 2>&1
echo ---- exit=%errorlevel% ----
echo.
echo ===== entries present =====
findstr /I "identifier description" "%OUT%"
echo.
echo ===== any hypervisor / iommu / vsm settings anywhere =====
findstr /I "hypervisor iommu vsmlaunchtype" "%OUT%"
echo.
echo ===== bootsequence / displayorder / default =====
findstr /I "bootsequence displayorder default" "%OUT%"

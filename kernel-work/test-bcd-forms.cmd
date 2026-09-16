@echo off
echo === bcdedit version/help header ===
bcdedit /? > "%TEMP%\bde-help.txt" 2>&1
type "%TEMP%\bde-help.txt" | findstr /I "version bcdedit"
echo.
echo === which entry specifiers PARSE (access denied) vs FAIL (invalid type) ===
echo -- /enum {current} --
bcdedit /enum {current} 2>&1 | findstr /I "denied invalid specified"
echo -- /enum {default} --
bcdedit /enum {default} 2>&1 | findstr /I "denied invalid specified"
echo -- /enum {bootmgr} --
bcdedit /enum {bootmgr} 2>&1 | findstr /I "denied invalid specified"
echo -- /enum ACTIVE --
bcdedit /enum ACTIVE 2>&1 | findstr /I "denied invalid specified"
echo -- /enum all --
bcdedit /enum all 2>&1 | findstr /I "denied invalid specified"
echo -- /enum firmware --
bcdedit /enum firmware 2>&1 | findstr /I "denied invalid specified"

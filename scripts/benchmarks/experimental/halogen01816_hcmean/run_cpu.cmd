@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 2
cl.exe /nologo /std:c++20 /W4 /WX /EHsc /O2 /MT test_plan.cpp /Fe:test_plan.exe /link /INCREMENTAL:NO
if errorlevel 1 exit /b 2
test_plan.exe

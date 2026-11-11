@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
cl.exe /nologo /std:c++20 /EHsc /W4 /Od /MT test_append_head_scope.cpp /Fe:test_append_head_scope.exe /Fo:test_append_head_scope.obj
exit /b %errorlevel%

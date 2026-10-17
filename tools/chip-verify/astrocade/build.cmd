@echo off
rem Builds and runs the core fidelity check with the VS2019 Build Tools compiler.
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~dp0"
if not exist out mkdir out
cl /nologo /O2 /EHsc /std:c++17 /Ishim /Ireference /Foout\ /Feout\fidelity.exe fidelity.cpp reference\astrocde.cpp ..\..\..\src\engine\platform\sound\astrocade.cpp || exit /b 1
for %%s in (1 2 3 4 5) do out\fidelity.exe %%s || exit /b 1

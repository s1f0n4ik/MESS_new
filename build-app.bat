@echo off
setlocal
cd /d "%~dp0frontend"

echo [1/4] checking sidecar
for /f "tokens=2" %%i in ('rustc -Vv ^| findstr /b host:') do set TRIPLE=%%i
if "%TRIPLE%"=="" (echo cannot detect rust target triple & goto :fail)
echo target triple: %TRIPLE%
if not exist "src-tauri\binaries\postcards-backend-%TRIPLE%.exe" (
    echo MISSING: src-tauri\binaries\postcards-backend-%TRIPLE%.exe
    echo Run build-backend.bat first.
    goto :fail
)

echo [2/4] npm install
call npm install || goto :fail

echo [3/4] vite build
call npm run build || goto :fail

echo [4/4] tauri build
call npx tauri build || goto :fail

echo.
echo OK. Installer:
dir /b src-tauri\target\release\bundle\nsis\*.exe
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
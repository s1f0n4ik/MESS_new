@echo off
setlocal
cd /d "%~dp0frontend"

echo [1/4] checking backend sidecar and PDF resource
for /f "tokens=2" %%i in ('rustc -Vv ^| findstr /b host:') do set TRIPLE=%%i
if "%TRIPLE%"=="" (echo cannot detect rust target triple & goto :fail)
echo target triple: %TRIPLE%
if not exist "src-tauri\binaries\postcards-backend-%TRIPLE%.exe" (
    echo MISSING: src-tauri\binaries\postcards-backend-%TRIPLE%.exe
    echo Run build-backend.bat first. This file is bundled next to tauri-app.exe.
    goto :fail
)
if not exist "src-tauri\pdfs-default\Postcards_2x2_template_14_blocks.pdf" (
    echo MISSING: src-tauri\pdfs-default\Postcards_2x2_template_14_blocks.pdf
    goto :fail
)

echo [2/4] npm install
call npm install || goto :fail

echo [3/4] vite build
call npm run build || goto :fail

echo [4/4] tauri build
call npx tauri build || goto :fail

echo.
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$json = [System.IO.File]::ReadAllText('src-tauri\tauri.conf.json'); $version = (ConvertFrom-Json $json).version; Join-Path (Resolve-Path 'src-tauri\target\release\bundle\nsis') ('Postcards_' + $version + '_x64-setup.exe')"`) do set INSTALLER=%%i
if not exist "%INSTALLER%" (echo Expected installer was not created: %INSTALLER% & goto :fail)
echo OK. Current installer:
echo %INSTALLER%
echo Older installers in the same folder are previous builds and can be archived or deleted.
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1

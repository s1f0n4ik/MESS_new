@echo off
setlocal
cd /d "%~dp0backend"

if not exist .venv (
    echo [1/4] creating venv
    python -m venv .venv || goto :fail
)

echo [2/4] installing deps
call .venv\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip || goto :fail
python -m pip install -r requirements.txt || goto :fail
python -m pip install pyinstaller || goto :fail

echo [3/4] building exe
rmdir /s /q build 2>nul
pyinstaller postcards-backend.spec --noconfirm || goto :fail

echo [4/4] copying to tauri binaries
for /f "tokens=2" %%i in ('rustc -Vv ^| findstr /b host:') do set TRIPLE=%%i
if "%TRIPLE%"=="" (echo cannot detect rust target triple & goto :fail)
echo target triple: %TRIPLE%

set DEST=..\frontend\src-tauri\binaries
if not exist "%DEST%" mkdir "%DEST%"
copy /y dist\postcards-backend.exe "%DEST%\postcards-backend-%TRIPLE%.exe" || goto :fail

echo.
echo OK: %DEST%\postcards-backend-%TRIPLE%.exe
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
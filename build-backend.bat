@echo off
setlocal
cd /d "%~dp0backend"

set PYEXE=py -3.12
%PYEXE% --version >nul 2>&1 || (echo Python 3.12 not found. Install from python.org & goto :fail)

if not exist .venv (
    echo [1/5] creating venv on Python 3.12
    %PYEXE% -m venv .venv || goto :fail
)

echo [2/5] checking venv version
call .venv\Scripts\activate.bat || goto :fail
for /f "tokens=2" %%v in ('python --version') do set PYVER=%%v
echo venv python: %PYVER%
echo %PYVER% | findstr /b "3.12." >nul || (echo venv is not 3.12 - delete .venv and rerun & goto :fail)

echo [3/5] installing deps
python -m pip install --upgrade pip || goto :fail
python -m pip install --only-binary=:all: -r requirements.txt || goto :fail
python -m pip install pyinstaller || goto :fail

echo [4/5] building exe
rmdir /s /q build 2>nul
pyinstaller postcards-backend.spec --noconfirm || goto :fail

echo [5/5] copying to tauri binaries
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
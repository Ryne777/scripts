@echo off
title Flash All - MSP430 BSL
setlocal

rem Usage:
rem   flash_all.bat COM16 firmware.bin
rem   flash_all.bat COM7 "C:\path with spaces\image.bin"
rem   No args: defaults (COM16, firmware.bin)

set PORT=COM16
set IMAGE=firmware.bin
if not "%~1"=="" set PORT=%~1
if not "%~2"=="" set IMAGE=%~2

cd /d "%~dp0"

echo ============================================================
echo   FLASH ALL: version - erase - write - read - compare
echo   Port: %PORT%   Image: %IMAGE%
echo ============================================================
echo.

if not exist "%IMAGE%" (
    echo [ERROR] Image file "%IMAGE%" not found!
    echo Put it next to this .bat or give a full path.
    echo.
    goto wait
)

echo [STEP 1] Check link: bsl_version.py
python bsl_version.py %PORT% --inv-rst --inv-test
if errorlevel 1 goto fail
echo.

echo [STEP 2] Mass erase: bsl_erase.py --all
echo (the script will ask for confirmation before erasing)
python bsl_erase.py %PORT% --inv-rst --inv-test --all
if errorlevel 1 goto fail
echo.

echo [STEP 3] Write firmware: bsl_write.py --write-info
python bsl_write.py %PORT% --inv-rst --inv-test --write-info %IMAGE%
if errorlevel 1 goto fail
echo.

echo [STEP 4] Read back: bsl_read.py --dump
python bsl_read.py %PORT% --inv-rst --inv-test --pwfile %IMAGE% --dump
if errorlevel 1 goto fail
echo.

echo [STEP 5] Compare: compare.py
python compare.py
if errorlevel 1 goto fail

echo.
echo ============================================================
echo   SUCCESS: all steps completed
echo ============================================================
goto wait

:fail
echo.
echo ============================================================
echo   FAILED: see the error message above
echo ============================================================

:wait
echo.
pause
endlocal

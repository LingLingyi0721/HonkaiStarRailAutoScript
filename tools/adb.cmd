@echo off
REM ============================================================
REM Project-local adb wrapper (for manual debugging).
REM
REM It enforces two things so we never collide with Alas:
REM   1. Use this project's own adb: tools\adb\adb.exe
REM   2. Force adb server port 5038 (Alas owns 5037)
REM
REM NOTE: keep this file ASCII-only! cmd.exe decodes .cmd files using
REM the system code page (GBK on zh-CN). Non-ASCII comments get mangled
REM into stray command fragments and break parsing.
REM
REM Usage (run from project root):
REM   tools\adb.cmd devices
REM   tools\adb.cmd -s 127.0.0.1:16416 shell getprop ro.product.model
REM
REM Verify isolation: python tools\devkit.py
REM ============================================================
setlocal
set ANDROID_ADB_SERVER_PORT=5038
"%~dp0adb\adb.exe" %*
endlocal
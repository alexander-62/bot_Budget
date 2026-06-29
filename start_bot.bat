@echo off
setlocal

cd /d "%~dp0"

call "%~dp0bot.bat" start --foreground
pause
endlocal

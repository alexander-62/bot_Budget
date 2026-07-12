@echo off
setlocal

cd /d "%~dp0"

call "%~dp0bot.bat" restart

endlocal

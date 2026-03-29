@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" manage_bot.py start --foreground
) else (
    python manage_bot.py start --foreground
)

endlocal

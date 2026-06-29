@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo === Остановка бота ===
if exist "manage_bot.py" (
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" manage_bot.py stop
    ) else (
        python manage_bot.py stop
    )
) else (
    echo manage_bot.py не найден, пропускаю остановку.
)

echo.
echo === Обновление из GitHub ===
git pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo Ошибка при обновлении репозитория.
    echo Проверь Git, сеть и наличие локальных изменений.
    pause
    exit /b 1
)

echo.
echo === Запуск бота ===
call start_bot.bat

endlocal

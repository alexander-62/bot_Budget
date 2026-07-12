@echo off
setlocal EnableExtensions

chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

cd /d "%~dp0"

if "%~1"=="" goto :Usage

if /I "%~1"=="start" goto :RunManager
if /I "%~1"=="stop" goto :RunManager
if /I "%~1"=="restart" goto :RunManager
if /I "%~1"=="status" goto :RunManager
if /I "%~1"=="update" goto :Update

goto :Usage

:RunManager
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" manage_bot.py %*
) else (
    python manage_bot.py %*
)
exit /b %errorlevel%

:Update
setlocal EnableExtensions

set "GIT_EXE="

call :FindGit
if not defined GIT_EXE (
    call :InstallGit
    if errorlevel 1 (
        echo.
        echo Git не установлен, и автоматическая установка не удалась.
        echo Установи Git for Windows вручную и запусти bat-файл еще раз.
        pause
        exit /b 1
    )
    call :FindGit
)

if not defined GIT_EXE (
    echo.
    echo Git все еще не найден после установки.
    pause
    exit /b 1
)

echo === Остановка бота ===
call :RunManager stop

echo.
echo === Обновление из GitHub ===
"%GIT_EXE%" fetch origin main
if errorlevel 1 (
    echo.
    echo Не удалось получить обновления из GitHub.
    pause
    exit /b 1
)

set "CURRENT_BRANCH="
for /f "usebackq delims=" %%I in (`"%GIT_EXE%" branch --show-current 2^>nul`) do set "CURRENT_BRANCH=%%I"
if /I not "%CURRENT_BRANCH%"=="main" (
    "%GIT_EXE%" switch main
    if errorlevel 1 (
        "%GIT_EXE%" switch -c main --track origin/main
        if errorlevel 1 (
            echo.
            echo Не удалось переключиться на main.
            pause
            exit /b 1
        )
    )
)

"%GIT_EXE%" pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo Ошибка при обновлении репозитория.
    echo Проверь сеть, Git и наличие локальных изменений.
    pause
    exit /b 1
)

echo.
echo === Установка зависимостей ===
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
) else (
    python -m pip install -r requirements.txt
)
if errorlevel 1 (
    echo.
    echo Не удалось установить зависимости из requirements.txt.
    pause
    exit /b 1
)

echo.
echo === Запуск бота ===
call :RunManager start

endlocal
exit /b 0

:FindGit
if defined GIT_EXE exit /b 0

where git >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%I in ('where git 2^>nul') do (
        set "GIT_EXE=%%I"
        goto :eof
    )
)

if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles%\Git\cmd\git.exe"
if defined GIT_EXE goto :eof

if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "GIT_EXE=%ProgramFiles(x86)%\Git\cmd\git.exe"
if defined GIT_EXE goto :eof

if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "GIT_EXE=%LocalAppData%\Programs\Git\cmd\git.exe"
goto :eof

:InstallGit
where winget >nul 2>nul
if errorlevel 1 (
    echo winget не найден.
    exit /b 1
)

echo Git не найден. Пытаюсь установить Git for Windows через winget...
winget install --id Git.Git -e --source winget --silent --accept-package-agreements --accept-source-agreements
exit /b %errorlevel%

:Usage
echo.
echo Usage:
echo   bot.bat start [--foreground]
echo   bot.bat stop
echo   bot.bat restart
echo   bot.bat status
echo   bot.bat update
echo.
echo Legacy wrappers are still available:
echo   start_bot.bat
echo   restart_bot.bat
echo   update_bot.bat
exit /b 1

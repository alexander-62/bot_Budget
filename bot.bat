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
if /I "%~1"=="tray" goto :RunManager
if /I "%~1"=="stop-tray" goto :RunManager
if /I "%~1"=="update" goto :Update

goto :Usage

:RunManager
call :FindPython
if errorlevel 1 exit /b 1

set "VENV_PY=.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        "%VENV_PY%" manage_bot.py %*
        exit /b %errorlevel%
    )
)

if /I "%~1"=="stop" (
    "%PYTHON_EXE%" manage_bot.py %*
    exit /b %errorlevel%
)
if /I "%~1"=="status" (
    "%PYTHON_EXE%" manage_bot.py %*
    exit /b %errorlevel%
)
if /I "%~1"=="stop-tray" (
    "%PYTHON_EXE%" manage_bot.py %*
    exit /b %errorlevel%
)

call :RepairVenv
if errorlevel 1 exit /b 1

"%VENV_PY%" manage_bot.py %*
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
call :FindPython
if errorlevel 1 exit /b 1

call :RepairVenv
if errorlevel 1 exit /b 1

call :InstallRequirements
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

:FindPython
if defined PYTHON_EXE exit /b 0

for /f "usebackq delims=" %%I in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do (
    set "PYTHON_EXE=%%I"
    goto :eof
)

for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do (
    set "PYTHON_EXE=%%I"
    goto :eof
)

echo.
echo Python не найден. Установи Python 3 и запусти bat-файл еще раз.
exit /b 1

:RepairVenv
set "VENV_PY=.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 exit /b 0
)

if exist ".venv" (
    echo.
    echo Локальное виртуальное окружение .venv повреждено или ссылается на отсутствующий Python.
    echo Пересоздаю .venv...
    rmdir /s /q ".venv"
)

"%PYTHON_EXE%" -m venv ".venv"
if errorlevel 1 (
    echo.
    echo Не удалось создать .venv через "%PYTHON_EXE%".
    exit /b 1
)

call :InstallRequirements
exit /b %errorlevel%

:InstallRequirements
".venv\Scripts\python.exe" -m pip install -r requirements.txt
exit /b %errorlevel%

:Usage
echo.
echo Usage:
echo   bot.bat start [--foreground]
echo   bot.bat stop
echo   bot.bat restart
echo   bot.bat status
echo   bot.bat tray
echo   bot.bat stop-tray
echo   bot.bat update
pause
exit /b 1

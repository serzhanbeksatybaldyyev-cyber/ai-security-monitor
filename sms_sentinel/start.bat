@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Sentinel

set "PY="
call :find_python
if not defined PY (
  echo Python 3.13 не найден. Устанавливаю Python 3.13...
  where py >nul 2>&1 && py install 3.13 --yes
  call :find_python
)
if not defined PY (
  echo Пробую установить через winget...
  winget install -e --id Python.Python.3.13 --scope user --accept-source-agreements --accept-package-agreements
  call :find_python
)
if not defined PY (
  echo.
  echo Не удалось найти или установить Python 3.13.
  echo Установите его вручную: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
echo Использую Python: %PY%

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] in [(3, 12), (3, 13)] else 1)" >nul 2>&1
  if errorlevel 1 (
    echo Старое окружение создано другой версией Python, пересоздаю...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo Создаю виртуальное окружение...
  "%PY%" -m venv .venv
  if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -c "import django, rest_framework, dotenv, yaml, sklearn, pandas, joblib" >nul 2>&1
if errorlevel 1 (
  echo Устанавливаю библиотеки, это займёт несколько минут...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --default-timeout 120 --retries 10 -r requirements-site.txt
  if errorlevel 1 goto failed
)

if not exist ".env" copy ".env.example" ".env" >nul

".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto failed
".venv\Scripts\python.exe" manage.py seed_demo

echo.
echo Сайт запускается: http://127.0.0.1:8000/
echo Администратор: admin / AdminDemo2026
echo Пользователь:  demo / DemoUser2026
echo Чтобы остановить сайт, закройте это окно или нажмите Ctrl+C.
echo.
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000/"
".venv\Scripts\python.exe" manage.py runserver
pause
exit /b 0

:find_python
for %%v in (3.13 3.12) do (
  if not defined PY if exist "%LOCALAPPDATA%\Python\pythoncore-%%v-64\python.exe" set "PY=%LOCALAPPDATA%\Python\pythoncore-%%v-64\python.exe"
)
for %%v in (313 312) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
  if not defined PY if exist "%ProgramFiles%\Python%%v\python.exe" set "PY=%ProgramFiles%\Python%%v\python.exe"
)
exit /b 0

:failed
echo.
echo Что-то пошло не так. Сделайте скриншот этого окна и пришлите его.
pause
exit /b 1

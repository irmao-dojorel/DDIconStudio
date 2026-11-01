@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto erro_pasta

set "PYTHONPATH=%~dp0src"
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "VENV=%LOCALAPPDATA%\DDIconStudio\venv"
set "VPY=%VENV%\Scripts\python.exe"
set "IMPORTS=import PIL, numpy, flet, xxhash, zstandard, ddiconstudio"

rem Venv ausente, quebrado (Python removido) ou com Python antigo: recria.
"%VPY%" -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto criar_venv

:verificar_dependencias
"%VPY%" -c "%IMPORTS%" >nul 2>&1
if errorlevel 1 goto instalar_dependencias
goto iniciar

:criar_venv
set "PY_BASE="
call :achar_python py -3
if not defined PY_BASE call :achar_python python
if not defined PY_BASE call :achar_python python3

set "USAR_UV="
if not defined PY_BASE (
    where uv >nul 2>&1
    if errorlevel 1 goto sem_python
    set "USAR_UV=1"
)

echo Criando o ambiente Python do DDIconStudio...
if exist "%VENV%" rmdir /s /q "%VENV%" >nul 2>&1
if defined USAR_UV (
    uv venv --clear --seed --python ">=3.10" "%VENV%"
) else (
    %PY_BASE% -m venv --clear "%VENV%"
)
if errorlevel 1 goto erro_venv
"%VPY%" -c "import sys" >nul 2>&1
if errorlevel 1 goto erro_venv
goto verificar_dependencias

:instalar_dependencias
echo Preparando o DDIconStudio para este perfil. Isso pode levar alguns minutos...
"%VPY%" -m ensurepip --upgrade >nul 2>&1
"%VPY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto erro_instalacao
"%VPY%" -m pip install --editable "%~dp0."
if errorlevel 1 goto erro_instalacao
"%VPY%" -c "%IMPORTS%"
if errorlevel 1 goto erro_instalacao

:iniciar
start "" /D "%~dp0" "%VENV%\Scripts\pythonw.exe" -m ddiconstudio
if errorlevel 1 goto erro_inicio
exit /b 0

rem Define PY_BASE com o comando informado se ele rodar o Python 3.10+.
:achar_python
%* -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 set "PY_BASE=%*"
exit /b 0

:sem_python
echo Python 3.10 ou superior nao foi encontrado. Instale-o em python.org e tente novamente.
goto falha

:erro_pasta
echo Nao foi possivel acessar a pasta do DDIconStudio.
goto falha

:erro_venv
echo Nao foi possivel criar o ambiente Python do DDIconStudio.
goto falha

:erro_instalacao
echo Falha ao instalar as dependencias. Verifique a conexao com a internet e tente novamente.
goto falha

:erro_inicio
echo Nao foi possivel iniciar o DDIconStudio.
goto falha

:falha
pause
exit /b 1

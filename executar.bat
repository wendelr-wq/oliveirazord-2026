@echo off
setlocal enabledelayedexpansion

title OLIVEIRAZORD 2026

echo.
echo Inicializando Oliveirazord 2026...
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual venv nao encontrado.
    echo Execute 'instalar.bat' antes de executar.
    pause
    exit /b 1
)

echo Ativando ambiente virtual...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERRO] Falha ao ativar o ambiente virtual.
    pause
    exit /b 1
)

echo Ambiente virtual ativado.
echo Iniciando aplicacao...
echo.

python main.py

if errorlevel 1 (
    echo.
    echo [ERRO] Programa encerrou com codigo %errorlevel%.
    pause
    exit /b 1
)

@echo off
setlocal enabledelayedexpansion

title OLIVEIRAZORD 2026

echo.
echo Inicializando Oliveirazord 2026...
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual venv nao encontrado ou incompleto.
    echo Execute 'instalar.bat' antes de executar.
    pause
    exit /b 1
)

echo Iniciando aplicacao com ambiente virtual...
echo.

venv\Scripts\python.exe main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Programa encerrou com codigo %errorlevel%.
    pause
    exit /b 1
)

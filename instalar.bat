@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: Definir código ESC para cores ANSI
set "ESC="
for /f %%a in ('powershell -NoProfile -Command "[char]27"') do set "ESC=%%a"

title OLIVEIRAZORD 2026 - INSTALADOR

cls
call :draw_banner
echo.
echo %ESC%[33m[*] Iniciando processo de configuração do Oliveirazord 2026...%ESC%[0m
echo.

:: 1. Verificar Python
echo   [ %ESC%[33mWAIT%ESC%[0m ] Verificando instalação do Python...
set "PYTHON_CMD="
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
) else (
    if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" (
        set "PYTHON_CMD=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
    ) else (
        py --version >nul 2>&1
        if %errorlevel% equ 0 (
            set "PYTHON_CMD=py"
        )
    )
)

if "%PYTHON_CMD%"=="" (
    cls
    call :draw_banner
    echo.
    echo   [ %ESC%[31mFAIL%ESC%[0m ] Verificando instalação do Python...
    echo.
    echo %ESC%[31m[ERRO] Python não foi encontrado no seu computador!%ESC%[0m
    echo Por favor, instale o Python 3.10+ e marque a opção "Add Python to PATH" durante a instalação.
    echo.
    pause
    exit /b 1
)

cls
call :draw_banner
echo.
echo   [  %ESC%[32mOK%ESC%[0m  ] Python encontrado no sistema.
echo.

:: 2. Remover VENV antiga (se existir) para evitar conflito de caminhos absolutos
if exist "venv" (
    echo   [ %ESC%[33mWAIT%ESC%[0m ] Removendo ambiente virtual anterior...
    rmdir /s /q "venv" >nul 2>&1
)

:: 3. Criar VENV
echo   [ %ESC%[33mWAIT%ESC%[0m ] Criando ambiente virtual venv...

:: Animação de progresso usando redraw da tela com ASCII puro
set "bar="
set "spaces=----------"
for /L %%i in (1,1,5) do (
    set "bar=!bar!##"
    set "spaces=!spaces:~2!"
    cls
    call :draw_banner
    echo.
    echo   [  %ESC%[32mOK%ESC%[0m  ] Python encontrado no sistema.
    echo.
    echo   [ %ESC%[33mWAIT%ESC%[0m ] Criando ambiente virtual venv... [!bar!!spaces!] %%i0/100
    ping -n 1 127.0.0.1 >nul
)

"%PYTHON_CMD%" -m venv venv >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   [ %ESC%[31mFAIL%ESC%[0m ] Falha ao criar o ambiente virtual venv.
    echo.
    pause
    exit /b 1
)

cls
call :draw_banner
echo.
echo   [  %ESC%[32mOK%ESC%[0m  ] Python encontrado no sistema.
echo   [  %ESC%[32mOK%ESC%[0m  ] Ambiente virtual venv criado com sucesso!
echo.

:: 4. Ativar VENV e Atualizar pip
echo   [ %ESC%[33mWAIT%ESC%[0m ] Ativando ambiente virtual...
call venv\Scripts\activate.bat >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   [ %ESC%[31mFAIL%ESC%[0m ] Falha ao ativar o venv.
    pause
    exit /b 1
)

cls
call :draw_banner
echo.
echo   [  %ESC%[32mOK%ESC%[0m  ] Python encontrado no sistema.
echo   [  %ESC%[32mOK%ESC%[0m  ] Ambiente virtual venv criado!
echo   [  %ESC%[32mOK%ESC%[0m  ] Ambiente virtual ativado.
echo.

echo   [ %ESC%[33mWAIT%ESC%[0m ] Atualizando o pip...
python -m pip install --upgrade pip >nul 2>&1

cls
call :draw_banner
echo.
echo   [  %ESC%[32mOK%ESC%[0m  ] Python encontrado no sistema.
echo   [  %ESC%[32mOK%ESC%[0m  ] Ambiente virtual venv criado!
echo   [  %ESC%[32mOK%ESC%[0m  ] Ambiente virtual ativado.
echo   [  %ESC%[32mOK%ESC%[0m  ] Pip atualizado.
echo.

:: 5. Instalar Dependências
echo %ESC%[36m[*] Instalando as dependências do requirements.txt...%ESC%[0m
echo %ESC%[90m(Isso pode levar alguns minutos. Por favor, aguarde...)%ESC%[0m
echo.

python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo   [ %ESC%[31mFAIL%ESC%[0m ] Falha ao instalar as dependências.
    pause
    exit /b 1
)

cls
call :draw_banner
echo.
echo   [  %ESC%[32mOK%ESC%[0m  ] Python encontrado no sistema.
echo   [  %ESC%[32mOK%ESC%[0m  ] Ambiente virtual venv criado!
echo   [  %ESC%[32mOK%ESC%[0m  ] Ambiente virtual ativado.
echo   [  %ESC%[32mOK%ESC%[0m  ] Pip atualizado.
echo   [  %ESC%[32mOK%ESC%[0m  ] Todas as dependências instaladas.
echo.

:: Finalização
echo %ESC%[32m================================================================%ESC%[0m
echo %ESC%[32m               INSTALAÇÃO CONCLUÍDA COM SUCESSO!                %ESC%[0m
echo %ESC%[32m                                                                %ESC%[0m
echo %ESC%[32m  Agora você pode usar o arquivo 'executar.bat' para rodar      %ESC%[0m
echo %ESC%[32m  o aplicativo de forma simples e direta.                       %ESC%[0m
echo %ESC%[32m================================================================%ESC%[0m
echo.
exit /b 0

:: ==========================================
:: ROTINA PARA DESENHAR O BANNER (SEM PIPES OU UNICODE)
:: ==========================================
:draw_banner
echo %ESC%[36m===============================================================%ESC%[0m
echo %ESC%[35m*   ____  _ _           _                               _     *%ESC%[0m
echo %ESC%[35m*  / __ \  (_)         (_)                             / /    *%ESC%[0m
echo %ESC%[35m* / /  \ \  _   _____ _ _ __ __ _ _______  _ __ __ _  / /     *%ESC%[0m
echo %ESC%[35m* / /  / / _ \ / / _ \ ^| '__/ _` \_  / _ \  '__/ _` \/ /      *%ESC%[0m
echo %ESC%[35m* \ \__/ / / \ \ V  __/ / / / (_/ // / (_) \ \ \ (_/  /       *%ESC%[0m
echo %ESC%[35m*  \____/ /_/   \___/_/_/_/  \__,_/___\___/ \_\  \__,_/_/     *%ESC%[0m
echo %ESC%[36m===============================================================%ESC%[0m
exit /b

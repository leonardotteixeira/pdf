@echo off
chcp 65001 >nul
title Formato Fácil PDF
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Primeira execucao: instalando o aplicativo...
    call "%~dp0instalar.bat" /auto
    if errorlevel 1 (
        echo.
        echo Nao foi possivel instalar. Veja as mensagens acima.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" iniciar.py
if errorlevel 1 pause

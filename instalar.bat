@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ================================================
echo   Formato Facil PDF - instalacao
echo ================================================
echo.

rem --- Python ---------------------------------------------------------------
set "PY="
where py >nul 2>nul && (py -3.12 -V >nul 2>nul && set "PY=py -3.12")
if not defined PY (where py >nul 2>nul && (py -3.11 -V >nul 2>nul && set "PY=py -3.11"))
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
    echo Python nao encontrado. Instale o Python 3.11 ou 3.12:
    echo     winget install Python.Python.3.12
    echo e execute este instalador novamente.
    exit /b 1
)
echo Usando: %PY%

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    %PY% -m venv .venv || exit /b 1
)
echo Instalando dependencias (pode levar alguns minutos)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || exit /b 1
echo Dependencias instaladas.
echo.

rem --- Tesseract OCR ---------------------------------------------------------
set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if exist "%TESS%" (
    echo Tesseract OCR encontrado.
) else (
    echo O Tesseract OCR ^(reconhecimento de texto em imagens^) nao esta instalado.
    echo Sem ele o aplicativo funciona, mas nao extrai texto de imagens e PDFs digitalizados.
    choice /c SN /m "Deseja instalar o Tesseract agora via winget"
    if not errorlevel 2 winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements
)

rem --- Idioma portugues para o OCR ------------------------------------------
if not exist "tessdata\por.traineddata" (
    echo Baixando o idioma portugues do OCR ^(cerca de 8 MB^)...
    if not exist tessdata mkdir tessdata
    curl -L -s -o "tessdata\por.traineddata" https://github.com/tesseract-ocr/tessdata_best/raw/main/por.traineddata
)
if exist "%ProgramFiles%\Tesseract-OCR\tessdata\eng.traineddata" if not exist "tessdata\eng.traineddata" copy /y "%ProgramFiles%\Tesseract-OCR\tessdata\eng.traineddata" tessdata\ >nul
if exist "%ProgramFiles%\Tesseract-OCR\tessdata\osd.traineddata" if not exist "tessdata\osd.traineddata" copy /y "%ProgramFiles%\Tesseract-OCR\tessdata\osd.traineddata" tessdata\ >nul
if exist "%ProgramFiles%\Tesseract-OCR\tessdata\configs" xcopy /e /i /y /q "%ProgramFiles%\Tesseract-OCR\tessdata\configs" tessdata\configs >nul

echo.
echo Instalacao concluida. Para usar, de dois cliques em iniciar.bat
if /i not "%~1"=="/auto" pause
exit /b 0

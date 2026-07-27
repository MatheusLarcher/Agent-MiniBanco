@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo  Agent-MiniBanco
echo  ------------------------------------------------
echo.

rem ---------------------------------------------------------------------------
rem 1. Ambiente virtual
rem ---------------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [1/4] Criando o ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo  ERRO: nao consegui criar o ambiente. O Python esta instalado?
        echo  Baixe em https://www.python.org/downloads/ e marque "Add to PATH".
        pause
        exit /b 1
    )
) else (
    echo  [1/4] Ambiente virtual ok.
)

set PY=.venv\Scripts\python.exe

rem ---------------------------------------------------------------------------
rem 2. Dependencias
rem    O marcador guarda o requirements.txt que foi instalado. Se o arquivo
rem    mudar, instala de novo sozinho.
rem    --only-binary evita que o pip tente compilar o litellm com Rust no 3.13.
rem ---------------------------------------------------------------------------
set MARCA=.venv\.requisitos-instalados
set PRECISA=1
if exist "%MARCA%" (
    fc /b "%MARCA%" requirements.txt >nul 2>&1 && set PRECISA=0
)
if "%PRECISA%"=="1" (
    echo  [2/4] Instalando as dependencias ^(demora uns 2 minutos na primeira vez^)...
    %PY% -m pip install --quiet --upgrade pip
    %PY% -m pip install --only-binary :all: -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  ERRO: a instalacao falhou. Veja a mensagem acima.
        pause
        exit /b 1
    )
    copy /y requirements.txt "%MARCA%" >nul
) else (
    echo  [2/4] Dependencias ok.
)

rem ---------------------------------------------------------------------------
rem 3. Configuracao e banco ficticio
rem ---------------------------------------------------------------------------
if not exist ".env" (
    copy /y .env.example .env >nul
    echo.
    echo  ------------------------------------------------
    echo   Falta a chave do LLM.
    echo   Vou abrir o arquivo .env no bloco de notas:
    echo   preencha a chave, salve e FECHE o bloco de notas
    echo   que eu continuo daqui.
    echo  ------------------------------------------------
    echo.
    notepad .env
    echo.
)

if not exist "data\banco.db" (
    echo  [3/4] Criando o banco ficticio...
    %PY% -m banco.seed
    if errorlevel 1 (
        echo.
        echo  ERRO: nao consegui criar o banco.
        pause
        exit /b 1
    )
) else (
    echo  [3/4] Banco ok.
)

rem ---------------------------------------------------------------------------
rem 4. Sobe o chat e abre o navegador
rem ---------------------------------------------------------------------------
echo  [4/4] Abrindo o chat em http://localhost:8010
echo.
echo  ------------------------------------------------
echo   Para fechar, aperte Ctrl+C nesta janela.
echo  ------------------------------------------------
echo.

start "" http://localhost:8010
%PY% -m app.server

endlocal

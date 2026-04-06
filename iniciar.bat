@echo off
title Calculo Feliciano Adv - SistPrev
color 0A
echo.
echo  ============================================
echo    CALCULO FELICIANO ADV - SistPrev
echo  ============================================
echo.
echo  Iniciando o sistema...
echo.

cd /d "C:\Users\Administrador\Documents\Documents\previdenciario"

:: Verificar se a porta ja esta em uso
netstat -ano | findstr ":8001" | findstr "LISTEN" >nul 2>&1
if %errorlevel%==0 (
    echo  Sistema ja esta rodando!
    echo  Abrindo no navegador...
    timeout /t 1 >nul
    start http://localhost:8001
    exit
)

:: Iniciar servidor em segundo plano
start /B python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 >nul 2>&1

echo  Aguardando servidor iniciar...
:esperar
timeout /t 2 >nul
curl -s http://localhost:8001 >nul 2>&1
if %errorlevel% neq 0 goto esperar

echo.
echo  Sistema pronto!
echo  Abrindo no navegador...
echo.
start http://localhost:8001

echo  ============================================
echo   Nao feche esta janela enquanto estiver
echo   usando o sistema.
echo  ============================================
echo.
echo  Para encerrar, feche esta janela.
echo.

:: Manter janela aberta
cmd /k

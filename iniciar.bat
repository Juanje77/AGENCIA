@echo off
REM Arranque del sistema en Windows. Se puede ejecutar con doble clic.
cd /d "%~dp0"
title Sistema de agencia de viajes

REM Busca el lanzador de Python: primero "py", despues "python".
set PY=
where py >nul 2>&1 && set PY=py
if not defined PY (where python >nul 2>&1 && set PY=python)

if not defined PY (
  echo.
  echo ==============================================================
  echo   No se encontro Python en esta computadora.
  echo.
  echo   Instalalo desde https://www.python.org/downloads/
  echo   IMPORTANTE: en la primera pantalla del instalador, tilda
  echo   la casilla "Add Python to PATH" antes de continuar.
  echo ==============================================================
  echo.
  pause
  exit /b 1
)

echo Iniciando el sistema...
echo.
%PY% iniciar.py
pause

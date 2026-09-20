#!/bin/bash
# Arranque del sistema en Mac. Se puede ejecutar con doble clic.
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo
  echo "=============================================================="
  echo "  No se encontro Python en esta computadora."
  echo "  Instalalo desde https://www.python.org/downloads/"
  echo "=============================================================="
  echo
  read -r -p "Apreta Enter para cerrar."
  exit 1
fi

echo "Iniciando el sistema..."
echo
"$PY" iniciar.py

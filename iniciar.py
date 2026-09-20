"""Arranque del sistema sin tener que instalar nada.

    python iniciar.py

Agrega src/ al path, revisa que este lo necesario, levanta el servidor y
abre el navegador. Pensado para arrancar con doble clic desde iniciar.bat
(Windows) o iniciar.command (Mac).
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SRC = RAIZ / "src"
PUERTO = int(os.environ.get("AGENCIA_PUERTO", "8000"))
HOST = os.environ.get("AGENCIA_HOST", "127.0.0.1")

MINIMO_PYTHON = (3, 10)


def _salir(mensaje: str, codigo: int = 1) -> None:
    print("\n" + "=" * 62)
    print(mensaje)
    print("=" * 62)
    if os.name == "nt":
        input("\nApreta Enter para cerrar esta ventana.")
    raise SystemExit(codigo)


def _controlar_python() -> None:
    if sys.version_info < MINIMO_PYTHON:
        actual = ".".join(str(x) for x in sys.version_info[:3])
        esperado = ".".join(str(x) for x in MINIMO_PYTHON)
        _salir(
            f"Este sistema necesita Python {esperado} o superior.\n"
            f"La version instalada es {actual}.\n\n"
            "Descarga la ultima desde https://www.python.org/downloads/"
        )


def _controlar_ubicacion() -> None:
    if not SRC.exists():
        _salir(
            "No se encuentra la carpeta 'src'.\n\n"
            f"Este archivo tiene que quedar junto a ella, dentro de la carpeta\n"
            f"del sistema. Ahora esta en:\n  {RAIZ}\n\n"
            "Si descomprimiste el ZIP, entra a la carpeta que se creo y abri\n"
            "el iniciar que esta adentro."
        )


def _avisar_dependencias() -> None:
    """Las dependencias son opcionales: el sistema arranca igual sin ellas."""
    faltan = []
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        try:
            import fitz  # noqa: F401
        except ImportError:
            faltan.append("pymupdf   (para leer facturas en PDF)")
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        faltan.append("openpyxl  (para planillas de Excel)")

    if faltan:
        print("\n  Falta instalar:")
        for item in faltan:
            print(f"    - {item}")
        print("\n  Instalalas con:")
        print(f"    {Path(sys.executable).name} -m pip install -r requirements.txt")
        print("\n  El sistema arranca igual, pero esas funciones no van a andar.\n")


def main() -> int:
    _controlar_python()
    _controlar_ubicacion()
    sys.path.insert(0, str(SRC))

    try:
        from agencia.web.servidor import correr
    except ImportError as exc:
        _salir(
            f"No se pudo cargar el sistema: {exc}\n\n"
            "Revisa que la carpeta este completa (que el ZIP se haya\n"
            "descomprimido entero)."
        )

    _avisar_dependencias()

    direccion = f"http://{HOST}:{PUERTO}"
    # Se abre el navegador en paralelo, cuando el servidor ya esta escuchando.
    threading.Timer(1.5, lambda: webbrowser.open(direccion)).start()

    try:
        correr(HOST, PUERTO)
    except OSError as exc:
        if getattr(exc, "errno", None) in (48, 98, 10048):
            _salir(
                f"El puerto {PUERTO} ya esta ocupado.\n\n"
                "Puede que el sistema ya este abierto en otra ventana:\n"
                f"  proba entrar a {direccion}\n\n"
                "Si no, arrancalo en otro puerto:\n"
                f"  AGENCIA_PUERTO=8001 {Path(sys.executable).name} iniciar.py"
            )
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

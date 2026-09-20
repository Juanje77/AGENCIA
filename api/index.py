"""Punto de entrada para Vercel.

Vercel invoca una funcion WSGI por peticion. El despachador de rutas es el
mismo que usa el servidor local: aca solo se traduce el formato.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from agencia.web.rutas import (  # noqa: E402
    LIMITE_PETICION,
    Peticion,
    Respuesta,
    despachar,
)


def _leer_cuerpo(entorno) -> dict:
    try:
        longitud = int(entorno.get("CONTENT_LENGTH") or 0)
    except ValueError:
        longitud = 0
    if longitud <= 0:
        return {}
    if longitud > LIMITE_PETICION:
        raise ValueError("La peticion es demasiado grande.")
    crudo = entorno["wsgi.input"].read(longitud)
    try:
        return json.loads(crudo.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalido: {exc}") from None


def _cabeceras(entorno) -> dict:
    cabeceras = {}
    for clave, valor in entorno.items():
        if clave.startswith("HTTP_"):
            cabeceras[clave[5:].replace("_", "-").title()] = valor
    return cabeceras


def app(entorno, iniciar_respuesta):
    """Aplicacion WSGI."""
    metodo = entorno.get("REQUEST_METHOD", "GET").upper()
    ruta = entorno.get("PATH_INFO", "/") or "/"

    try:
        cuerpo = _leer_cuerpo(entorno) if metodo == "POST" else {}
        respuesta = despachar(
            Peticion(metodo=metodo, ruta=ruta, cuerpo=cuerpo, cabeceras=_cabeceras(entorno))
        )
    except ValueError as exc:
        respuesta = Respuesta.error(400, str(exc))
    except Exception as exc:  # pragma: no cover - red de seguridad
        traceback.print_exc()
        respuesta = Respuesta.error(500, f"Error inesperado: {exc}")

    iniciar_respuesta(
        f"{respuesta.codigo} {_texto_estado(respuesta.codigo)}",
        [
            ("Content-Type", respuesta.tipo),
            ("Content-Length", str(len(respuesta.cuerpo))),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "same-origin"),
        ],
    )
    return [respuesta.cuerpo]


def _texto_estado(codigo: int) -> str:
    return {
        200: "OK", 400: "Bad Request", 401: "Unauthorized",
        404: "Not Found", 405: "Method Not Allowed", 500: "Internal Server Error",
    }.get(codigo, "OK")


# Vercel tambien acepta el nombre 'handler'.
handler = app

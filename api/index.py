"""Punto de entrada para Vercel.

Vercel invoca una funcion WSGI por peticion. El despachador de rutas es el
mismo que usa el servidor local: aca solo se traduce el formato.

Si el sistema no llega a cargar -falta una dependencia, el paquete no entro en
el bundle-, en vez de un error generico del hosting se devuelve una pagina que
dice exactamente que fallo. Diagnosticar un despliegue a ciegas es lo que mas
tiempo hace perder.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# El import se hace acá y se guarda el error, para poder contarlo despues.
_ERROR_DE_CARGA: str | None = None
try:
    from agencia.web.rutas import LIMITE_PETICION, Peticion, Respuesta, despachar
except Exception:  # pragma: no cover - solo se ve si el despliegue esta roto
    _ERROR_DE_CARGA = traceback.format_exc()
    LIMITE_PETICION = 80 * 1024 * 1024


def _diagnostico() -> dict:
    """Que hay realmente en el servidor, para saber que falta."""
    def existe(ruta: Path) -> bool:
        try:
            return ruta.exists()
        except OSError:
            return False

    librerias = {}
    for nombre in ("pymupdf", "fitz", "openpyxl", "anthropic", "pytesseract"):
        try:
            __import__(nombre)
            librerias[nombre] = "instalada"
        except Exception as exc:
            librerias[nombre] = f"falta ({type(exc).__name__})"

    return {
        "python": platform.python_version(),
        "raiz": str(RAIZ),
        "src_presente": existe(SRC),
        "paquete_presente": existe(SRC / "agencia" / "__init__.py"),
        "estaticos_presentes": existe(SRC / "agencia" / "web" / "estatico" / "index.html"),
        "config_presente": existe(RAIZ / "config" / "parametros_fiscales.json"),
        "archivos_en_la_raiz": sorted(p.name for p in RAIZ.iterdir())[:30]
        if existe(RAIZ) else [],
        "librerias": librerias,
        "en_vercel": bool(os.environ.get("VERCEL")),
        "clave_configurada": bool(os.environ.get("AGENCIA_CLAVE")),
        "ia_configurada": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


def _pagina_de_error() -> bytes:
    """Pagina legible con el motivo y el diagnostico, en vez de un 500 pelado."""
    from html import escape

    datos = _diagnostico()
    filas = "".join(
        f"<tr><td>{escape(str(k))}</td><td><code>{escape(str(v))}</code></td></tr>"
        for k, v in datos.items()
    )
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>El sistema no pudo arrancar</title><style>
body{{font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
background:#EEF1EC;color:#1F2D2B;margin:0;padding:32px 18px}}
.hoja{{max-width:820px;margin:0 auto;background:#fff;border:1px solid #D7DED7;
border-radius:6px;padding:30px}}
h1{{font-size:21px;margin:0 0 6px;color:#A6392D}}
p{{color:#5B6B64}}
pre{{background:#1F2D2B;color:#EEF1EC;padding:14px;border-radius:5px;
overflow-x:auto;font-size:12.5px;line-height:1.45}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
td{{padding:6px 8px;border-bottom:1px solid #E6EAE4;vertical-align:top}}
td:first-child{{color:#5B6B64;width:190px}}
code{{font-family:ui-monospace,monospace;font-size:12.5px}}
h2{{font-size:14px;text-transform:uppercase;letter-spacing:.05em;color:#5B6B64;
margin:24px 0 8px}}
</style></head><body><div class="hoja">
<h1>El sistema no pudo arrancar</h1>
<p>El servidor respondió, así que el despliegue existe, pero el código no llegó
a cargarse. Abajo está el motivo exacto y qué encontró el servidor.</p>
<h2>Motivo</h2>
<pre>{escape(_ERROR_DE_CARGA or "sin detalle")}</pre>
<h2>Qué hay en el servidor</h2>
<table><tbody>{filas}</tbody></table>
<h2>Qué suele ser</h2>
<p>Si <code>paquete_presente</code> dice <code>False</code>, el código no entró
en el paquete de la función: revisá <code>includeFiles</code> en
<code>vercel.json</code>. Si alguna librería dice <code>falta</code>, no se
instaló <code>requirements.txt</code>.</p>
</div></body></html>""".encode("utf-8")


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
    return {
        clave[5:].replace("_", "-").title(): valor
        for clave, valor in entorno.items()
        if clave.startswith("HTTP_")
    }


def app(entorno, iniciar_respuesta):
    """Aplicacion WSGI."""
    metodo = entorno.get("REQUEST_METHOD", "GET").upper()
    ruta = entorno.get("PATH_INFO", "/") or "/"

    # Diagnostico: siempre disponible, aunque el resto no cargue.
    if ruta in ("/api/estado", "/estado"):
        cuerpo = json.dumps(
            {"carga": "error" if _ERROR_DE_CARGA else "ok", **_diagnostico()},
            ensure_ascii=False, indent=2, default=str,
        ).encode("utf-8")
        return _responder(iniciar_respuesta, 200, "application/json; charset=utf-8", cuerpo)

    if _ERROR_DE_CARGA:
        return _responder(iniciar_respuesta, 500, "text/html; charset=utf-8", _pagina_de_error())

    try:
        cuerpo_json = _leer_cuerpo(entorno) if metodo == "POST" else {}
        respuesta = despachar(
            Peticion(metodo=metodo, ruta=ruta, cuerpo=cuerpo_json, cabeceras=_cabeceras(entorno))
        )
    except ValueError as exc:
        respuesta = Respuesta.error(400, str(exc))
    except Exception as exc:  # pragma: no cover - red de seguridad
        traceback.print_exc()
        respuesta = Respuesta.error(500, f"Error inesperado: {exc}")

    return _responder(iniciar_respuesta, respuesta.codigo, respuesta.tipo, respuesta.cuerpo)


def _responder(iniciar_respuesta, codigo: int, tipo: str, cuerpo: bytes):
    iniciar_respuesta(
        f"{codigo} {_texto_estado(codigo)}",
        [
            ("Content-Type", tipo),
            ("Content-Length", str(len(cuerpo))),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "same-origin"),
        ],
    )
    return [cuerpo]


def _texto_estado(codigo: int) -> str:
    return {
        200: "OK", 400: "Bad Request", 401: "Unauthorized",
        404: "Not Found", 405: "Method Not Allowed", 500: "Internal Server Error",
    }.get(codigo, "OK")


# Vercel tambien acepta el nombre 'handler'.
handler = app

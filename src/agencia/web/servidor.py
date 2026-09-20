"""Servidor local con la biblioteca estandar: no hace falta instalar nada.

    python -m agencia.web

Traduce la peticion HTTP y delega en el despachador de rutas, que es el mismo
que usa el despliegue en Vercel.
"""

from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .rutas import LIMITE_PETICION, Peticion, Respuesta, despachar


class Manejador(BaseHTTPRequestHandler):
    server_version = "AgenciaViajes/1.0"

    def log_message(self, formato: str, *args) -> None:
        print(f"  {self.address_string()} {formato % args}")

    def do_GET(self) -> None:
        self._atender("GET")

    def do_POST(self) -> None:
        self._atender("POST")

    def _atender(self, metodo: str) -> None:
        try:
            cuerpo = self._cuerpo() if metodo == "POST" else {}
        except ValueError as exc:
            return self._responder(Respuesta.error(400, str(exc)))

        try:
            respuesta = despachar(
                Peticion(
                    metodo=metodo,
                    ruta=urlparse(self.path).path,
                    cuerpo=cuerpo,
                    cabeceras=dict(self.headers.items()),
                )
            )
        except Exception as exc:  # pragma: no cover - red de seguridad
            traceback.print_exc()
            respuesta = Respuesta.error(500, f"Error inesperado: {exc}")
        self._responder(respuesta)

    def _cuerpo(self) -> dict:
        longitud = int(self.headers.get("Content-Length") or 0)
        if longitud <= 0:
            raise ValueError("La peticion llego sin datos.")
        if longitud > LIMITE_PETICION:
            raise ValueError("La peticion es demasiado grande.")
        try:
            return json.loads(self.rfile.read(longitud).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalido: {exc}") from None

    def _responder(self, respuesta: Respuesta) -> None:
        self.send_response(respuesta.codigo)
        self.send_header("Content-Type", respuesta.tipo)
        self.send_header("Content-Length", str(len(respuesta.cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(respuesta.cuerpo)


def correr(host: str = "127.0.0.1", puerto: int = 8000) -> None:
    servidor = ThreadingHTTPServer((host, puerto), Manejador)
    print("\n  Sistema de agencia de viajes")
    print(f"  Abri http://{host}:{puerto} en el navegador")
    print("  Ctrl+C para detener\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  Servidor detenido.")
    finally:
        servidor.server_close()

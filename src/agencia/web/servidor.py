"""Servidor web con la biblioteca estandar: no hace falta instalar nada.

    python -m agencia.web

Expone la interfaz y una API JSON:
    GET  /api/parametros        opciones para los formularios
    GET  /api/mayoristas        padron de mayoristas y datos de la agencia
    POST /api/mayoristas        guarda el padron
    POST /api/cotizacion        calcula una cotizacion por opciones
    POST /api/cotizacion/html   vista para el cliente o para la agencia
    POST /api/facturas          lee facturas PDF y devuelve las operaciones
    POST /api/periodo           liquida el IVA e Ingresos Brutos del periodo
    POST /api/periodo/html      informe imprimible del periodo
"""

from __future__ import annotations

import base64
import json
import tempfile
import traceback
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..config import cargar_parametros
from ..liquidaciones import ErrorDeLectura
from ..liquidaciones.factura import leer_factura
from ..liquidador import cargar_padron, guardar_padron, operacion_desde_comprobante
from ..presupuestos.cotizacion import TIPOS_SERVICIO, calcular_cotizacion
from .informes import informe_cotizacion_agencia, informe_cotizacion_cliente, informe_periodo
from .mapeo import (
    DatosInvalidos,
    cotizacion_desde_dict,
    padron_desde_dict,
    periodo_desde_dict,
)

ESTATICO = Path(__file__).parent / "estatico"
LIMITE_ARCHIVO = 25 * 1024 * 1024
LIMITE_PETICION = 80 * 1024 * 1024
MAX_ARCHIVOS = 40


class Manejador(BaseHTTPRequestHandler):
    server_version = "AgenciaViajes/1.0"

    def log_message(self, formato: str, *args) -> None:
        print(f"  {self.address_string()} {formato % args}")

    # --- rutas ------------------------------------------------------------

    def do_GET(self) -> None:
        ruta = urlparse(self.path).path
        try:
            if ruta in ("/", "/index.html"):
                return self._estatico("index.html", "text/html; charset=utf-8")
            if ruta == "/api/parametros":
                return self._json(self._parametros())
            if ruta == "/api/mayoristas":
                return self._json(cargar_padron().a_dict())
            if ruta.startswith("/estatico/"):
                nombre = ruta[len("/estatico/") :]
                return self._estatico(nombre, self._tipo(nombre))
            self._error(404, "Recurso no encontrado")
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self._error(500, f"Error inesperado: {exc}")

    def do_POST(self) -> None:
        ruta = urlparse(self.path).path
        try:
            if ruta == "/api/cotizacion":
                datos = self._cuerpo()
                return self._json(calcular_cotizacion(cotizacion_desde_dict(datos)).a_dict())
            if ruta == "/api/cotizacion/html":
                datos = self._cuerpo()
                calculada = calcular_cotizacion(cotizacion_desde_dict(datos))
                vista = informe_cotizacion_agencia if datos.get("vista") == "agencia" else informe_cotizacion_cliente
                return self._html(vista(calculada))
            if ruta == "/api/facturas":
                return self._json(self._leer_facturas())
            if ruta == "/api/periodo":
                return self._json(periodo_desde_dict(self._cuerpo()).a_dict())
            if ruta == "/api/periodo/html":
                return self._html(informe_periodo(periodo_desde_dict(self._cuerpo())))
            if ruta == "/api/mayoristas":
                padron = padron_desde_dict(self._cuerpo())
                guardar_padron(padron)
                return self._json(padron.a_dict())
            self._error(404, "Recurso no encontrado")
        except (DatosInvalidos, ErrorDeLectura, ValueError, KeyError) as exc:
            self._error(400, str(exc))
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self._error(500, f"Error inesperado: {exc}")

    # --- handlers ---------------------------------------------------------

    def _parametros(self) -> dict:
        params = cargar_parametros()
        padron = cargar_padron()
        return {
            "version": params.version,
            "aviso": params.aviso,
            "tipos_servicio": [
                {"nombre": nombre, "fiscal": fiscal}
                for nombre, fiscal in TIPOS_SERVICIO.items()
            ],
            "servicios_fiscales": [
                {"codigo": s.codigo, "etiqueta": s.etiqueta, "nota": s.nota}
                for s in sorted(params.servicios.values(), key=lambda x: x.etiqueta)
            ],
            "jurisdicciones": [
                {"codigo": j.codigo, "etiqueta": j.etiqueta, "alicuota": str(j.alicuota)}
                for j in sorted(params.jurisdicciones.values(), key=lambda x: x.etiqueta)
            ],
            "agencia": padron.a_dict()["agencia"],
            "mayoristas": [m.a_dict() for m in padron.mayoristas],
            "advertencias": params.advertencias_de_configuracion(),
        }

    def _leer_facturas(self) -> dict:
        """Lee los PDF subidos y devuelve una operacion por factura."""
        datos = self._cuerpo()
        archivos = datos.get("archivos") or []
        if not archivos:
            raise DatosInvalidos("No se recibio ningun archivo.")
        if len(archivos) > MAX_ARCHIVOS:
            raise DatosInvalidos(
                f"Son {len(archivos)} archivos y el maximo por vez es {MAX_ARCHIVOS}."
            )

        padron = cargar_padron()
        cuit = str(datos.get("cuit_agencia") or padron.agencia.cuit or "")
        servicio_propio = datos.get("servicio_propio_pct") or 0

        operaciones, errores = [], []
        for archivo in archivos:
            nombre = str(archivo.get("nombre") or "sin-nombre.pdf")
            try:
                comprobante = self._leer_una(archivo, nombre, cuit)
            except (DatosInvalidos, ErrorDeLectura, ValueError) as exc:
                errores.append({"archivo": nombre, "error": str(exc)})
                continue
            operacion = operacion_desde_comprobante(comprobante, padron, servicio_propio)
            operaciones.append(
                {**operacion.a_dict(), "comprobante_detalle": comprobante.a_dict()}
            )

        return {"operaciones": operaciones, "errores": errores}

    def _leer_una(self, archivo: dict, nombre: str, cuit: str):
        contenido = archivo.get("contenido")
        if not contenido:
            raise DatosInvalidos("El archivo llego vacio.")
        try:
            binario = base64.b64decode(contenido, validate=True)
        except Exception:
            raise DatosInvalidos("El archivo llego corrupto. Volve a subirlo.") from None
        if len(binario) > LIMITE_ARCHIVO:
            raise DatosInvalidos(
                f"Supera el limite de {LIMITE_ARCHIVO // (1024 * 1024)} MB."
            )

        sufijo = Path(nombre).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=sufijo, delete=False) as temporal:
            temporal.write(binario)
            ruta = Path(temporal.name)
        try:
            comprobante = leer_factura(ruta, cuit_agencia=cuit)
            comprobante.archivo = nombre
            return comprobante
        finally:
            ruta.unlink(missing_ok=True)

    # --- utilidades -------------------------------------------------------

    def _cuerpo(self) -> dict:
        longitud = int(self.headers.get("Content-Length") or 0)
        if longitud <= 0:
            raise DatosInvalidos("La peticion llego sin datos.")
        if longitud > LIMITE_PETICION:
            raise DatosInvalidos("La peticion es demasiado grande.")
        try:
            return json.loads(self.rfile.read(longitud).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DatosInvalidos(f"JSON invalido: {exc}") from None

    def _estatico(self, nombre: str, tipo: str) -> None:
        ruta = (ESTATICO / nombre).resolve()
        if not ruta.is_relative_to(ESTATICO.resolve()) or not ruta.exists():
            return self._error(404, "Archivo no encontrado")
        self._responder(200, ruta.read_bytes(), tipo)

    def _json(self, datos) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
        self._responder(200, cuerpo, "application/json; charset=utf-8")

    def _html(self, texto: str) -> None:
        self._responder(200, texto.encode("utf-8"), "text/html; charset=utf-8")

    def _error(self, codigo: int, mensaje: str) -> None:
        cuerpo = json.dumps({"error": mensaje}, ensure_ascii=False).encode("utf-8")
        self._responder(codigo, cuerpo, "application/json; charset=utf-8")

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(cuerpo)

    @staticmethod
    def _tipo(nombre: str) -> str:
        if nombre.endswith(".css"):
            return "text/css; charset=utf-8"
        if nombre.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if nombre.endswith(".html"):
            return "text/html; charset=utf-8"
        return "application/octet-stream"


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

"""Las rutas de la aplicacion, sin atarse a como llega la peticion.

El mismo despachador atiende el servidor local (http.server) y el despliegue
en Vercel (WSGI). Lo unico que cambia entre uno y otro es quien traduce la
peticion y quien guarda la configuracion.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import cargar_parametros
from ..liquidaciones import ErrorDeLectura
from ..liquidaciones.factura import leer_factura
from ..liquidador import Padron, cargar_padron, guardar_padron, operacion_desde_comprobante
from ..presupuestos.cotizacion import TIPOS_SERVICIO, calcular_cotizacion
from .informes import (
    informe_cotizacion_agencia,
    informe_cotizacion_cliente,
    informe_periodo,
)
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

JSON = "application/json; charset=utf-8"
HTML = "text/html; charset=utf-8"


def solo_lectura() -> bool:
    """En un hosting serverless el disco no se puede escribir.

    Ahi la configuracion la guarda el navegador y viaja en cada peticion, que
    ademas deja los datos de la agencia en su propia computadora.
    """
    if os.environ.get("AGENCIA_SOLO_LECTURA"):
        return os.environ["AGENCIA_SOLO_LECTURA"] not in ("0", "false", "no")
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def clave_de_acceso() -> str:
    return os.environ.get("AGENCIA_CLAVE", "").strip()


@dataclass
class Peticion:
    metodo: str
    ruta: str
    cuerpo: dict = field(default_factory=dict)
    cabeceras: dict = field(default_factory=dict)

    def cabecera(self, nombre: str, default: str = "") -> str:
        buscado = nombre.lower()
        for clave, valor in self.cabeceras.items():
            if clave.lower() == buscado:
                return valor
        return default


@dataclass
class Respuesta:
    codigo: int
    tipo: str
    cuerpo: bytes

    @classmethod
    def json(cls, datos: Any, codigo: int = 200) -> "Respuesta":
        return cls(codigo, JSON, json.dumps(datos, ensure_ascii=False, default=str).encode())

    @classmethod
    def html(cls, texto: str, codigo: int = 200) -> "Respuesta":
        return cls(codigo, HTML, texto.encode("utf-8"))

    @classmethod
    def error(cls, codigo: int, mensaje: str) -> "Respuesta":
        return cls.json({"error": mensaje}, codigo)


def despachar(peticion: Peticion) -> Respuesta:
    """Resuelve una peticion y devuelve la respuesta ya armada."""
    negado = _controlar_acceso(peticion)
    if negado is not None:
        return negado

    try:
        if peticion.metodo == "GET":
            return _get(peticion)
        if peticion.metodo == "POST":
            return _post(peticion)
        return Respuesta.error(405, f"Metodo no permitido: {peticion.metodo}")
    except (DatosInvalidos, ErrorDeLectura, ValueError, KeyError) as exc:
        return Respuesta.error(400, str(exc))


RUTAS_PANEL = ("/panel", "/panel/", "/panel/index.html")
RUTAS_PUBLICAS_DE_PAGINA = ("/", "/index.html", "/publico.html") + RUTAS_PANEL


def _controlar_acceso(peticion: Peticion) -> Respuesta | None:
    """Clave compartida, para cuando el sistema queda publicado en internet.

    La pagina del panel se puede cargar sin clave -es solo el cascaron-, pero
    ninguna llamada a la API funciona sin ella. El sitio publico (/) nunca la
    pide: es lo que ve un cliente potencial, no personal de la agencia.
    """
    clave = clave_de_acceso()
    if not clave:
        return None
    if peticion.ruta in RUTAS_PUBLICAS_DE_PAGINA or peticion.ruta.startswith("/estatico/"):
        return None
    if peticion.cabecera("X-Clave") == clave:
        return None
    return Respuesta.error(401, "Clave incorrecta o ausente.")


def _get(peticion: Peticion) -> Respuesta:
    ruta = peticion.ruta
    if ruta in ("/", "/index.html"):
        return _estatico("publico.html")
    if ruta in RUTAS_PANEL:
        return _estatico("index.html")
    if ruta == "/api/parametros":
        return Respuesta.json(_parametros())
    if ruta == "/api/mayoristas":
        return Respuesta.json(cargar_padron().a_dict())
    if ruta.startswith("/estatico/"):
        return _estatico(ruta[len("/estatico/") :])
    return Respuesta.error(404, "Recurso no encontrado")


def _post(peticion: Peticion) -> Respuesta:
    ruta, datos = peticion.ruta, peticion.cuerpo

    if ruta == "/api/cotizacion":
        return Respuesta.json(calcular_cotizacion(cotizacion_desde_dict(datos)).a_dict())

    if ruta == "/api/cotizacion/html":
        calculada = calcular_cotizacion(cotizacion_desde_dict(datos))
        vista = (
            informe_cotizacion_agencia
            if datos.get("vista") == "agencia"
            else informe_cotizacion_cliente
        )
        return Respuesta.html(vista(calculada))

    if ruta == "/api/facturas":
        return Respuesta.json(_leer_facturas(datos))

    if ruta == "/api/periodo":
        return Respuesta.json(periodo_desde_dict(datos).a_dict())

    if ruta == "/api/periodo/html":
        return Respuesta.html(informe_periodo(periodo_desde_dict(datos)))

    if ruta == "/api/mayoristas":
        return _guardar_mayoristas(datos)

    return Respuesta.error(404, "Recurso no encontrado")


def _parametros() -> dict:
    params = cargar_parametros()
    padron = cargar_padron()
    return {
        "version": params.version,
        "aviso": params.aviso,
        "solo_lectura": solo_lectura(),
        "hay_ocr": _hay_ocr(),
        "hay_ia": _hay_ia(),
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


def _hay_ocr() -> bool:
    """El OCR necesita el motor Tesseract, que no existe en un hosting serverless."""
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _hay_ia() -> bool:
    from ..liquidaciones.lectura_ia import hay_ia

    return hay_ia()


def _guardar_mayoristas(datos: dict) -> Respuesta:
    padron = padron_desde_dict(datos)
    if solo_lectura():
        # El disco no se puede escribir: se valida y lo guarda el navegador.
        return Respuesta.json({**padron.a_dict(), "guardado_en_disco": False})
    guardar_padron(padron)
    return Respuesta.json({**padron.a_dict(), "guardado_en_disco": True})


def _padron_de(datos: dict) -> Padron:
    """El padron llega desde el navegador o, si no vino, del archivo."""
    if isinstance(datos.get("padron"), dict) and datos["padron"].get("mayoristas"):
        return padron_desde_dict(datos["padron"])
    return cargar_padron()


def _leer_facturas(datos: dict) -> dict:
    archivos = datos.get("archivos") or []
    if not archivos:
        raise DatosInvalidos("No se recibio ningun archivo.")
    if len(archivos) > MAX_ARCHIVOS:
        raise DatosInvalidos(
            f"Son {len(archivos)} archivos y el maximo por vez es {MAX_ARCHIVOS}."
        )

    padron = _padron_de(datos)
    cuit = str(datos.get("cuit_agencia") or padron.agencia.cuit or "")
    servicio_propio = datos.get("servicio_propio_pct") or 0
    usar_ia = str(datos.get("usar_ia") or "auto").lower()
    if usar_ia not in ("auto", "nunca", "siempre"):
        raise DatosInvalidos(
            f"Valor invalido para usar_ia: {usar_ia!r}. Opciones: auto, nunca, siempre."
        )

    operaciones, errores = [], []
    for archivo in archivos:
        nombre = str(archivo.get("nombre") or "sin-nombre.pdf")
        try:
            comprobante = _leer_una(archivo, nombre, cuit, usar_ia)
        except (DatosInvalidos, ErrorDeLectura, ValueError) as exc:
            errores.append({"archivo": nombre, "error": str(exc)})
            continue
        operacion = operacion_desde_comprobante(comprobante, padron, servicio_propio)
        operaciones.append({**operacion.a_dict(), "comprobante_detalle": comprobante.a_dict()})

    return {"operaciones": operaciones, "errores": errores}


def _leer_una(archivo: dict, nombre: str, cuit: str, usar_ia: str = "auto"):
    contenido = archivo.get("contenido")
    if not contenido:
        raise DatosInvalidos("El archivo llego vacio.")
    try:
        binario = base64.b64decode(contenido, validate=True)
    except Exception:
        raise DatosInvalidos("El archivo llego corrupto. Volve a subirlo.") from None
    if len(binario) > LIMITE_ARCHIVO:
        raise DatosInvalidos(f"Supera el limite de {LIMITE_ARCHIVO // (1024 * 1024)} MB.")

    sufijo = Path(nombre).suffix or ".pdf"
    # En serverless el unico lugar escribible es el temporal del sistema.
    with tempfile.NamedTemporaryFile(suffix=sufijo, delete=False) as temporal:
        temporal.write(binario)
        ruta = Path(temporal.name)
    try:
        comprobante = leer_factura(ruta, cuit_agencia=cuit, usar_ia=usar_ia)
        comprobante.archivo = nombre
        return comprobante
    finally:
        ruta.unlink(missing_ok=True)


def _estatico(nombre: str) -> Respuesta:
    ruta = (ESTATICO / nombre).resolve()
    if not ruta.is_relative_to(ESTATICO.resolve()) or not ruta.exists():
        return Respuesta.error(404, "Archivo no encontrado")
    return Respuesta(200, tipo_de(nombre), ruta.read_bytes())


def tipo_de(nombre: str) -> str:
    if nombre.endswith(".css"):
        return "text/css; charset=utf-8"
    if nombre.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if nombre.endswith(".html"):
        return HTML
    if nombre.endswith(".json"):
        return JSON
    if nombre.endswith(".svg"):
        return "image/svg+xml"
    return "application/octet-stream"

"""Lectura de facturas con un modelo de lenguaje, como respaldo del parser.

El parser de `factura.py` no cuesta nada y responde en centesimas de segundo,
pero solo entiende los formatos para los que tiene reglas. Cuando una factura
no cierra o directamente no se puede leer -por ejemplo, un escaneo donde no hay
OCR disponible-, se le pasa el PDF a un modelo con vision.

El modelo lee, pero no decide: lo que devuelve pasa por el mismo control
aritmetico que el parser. Si los importes no suman el total, la factura queda
marcada igual. Un modelo puede equivocarse en un digito y eso, en una
liquidacion de impuestos, no puede pasar inadvertido.
"""

from __future__ import annotations

import base64
import json
import os
from decimal import Decimal
from pathlib import Path

from ..dinero import CERO, dec
from .factura import COMPRA, VENTA, Comprobante, ConceptoFactura, _controlar
from .lectores.base import ErrorDeLectura

MODELO_DEFAULT = "claude-opus-5"
MAX_TOKENS = 4096

# Una factura de una o dos paginas entra holgada; mas que eso suele ser un lote
# escaneado junto, que conviene separar antes de mandarlo.
LIMITE_MB = 8


class ErrorDeIA(ErrorDeLectura):
    """Fallo la lectura con el modelo."""


def hay_ia() -> bool:
    """Si estan la libreria y la credencial para poder usar el modelo."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def modelo_configurado() -> str:
    return os.environ.get("AGENCIA_MODELO_IA", MODELO_DEFAULT)


ESQUEMA = {
    "type": "object",
    "properties": {
        "clase": {
            "type": "string",
            "enum": ["FACTURA", "NOTA DE CREDITO", "NOTA DE DEBITO",
                     "FACTURA DE CREDITO", "RECIBO", "LIQUIDACION", "OTRO"],
            "description": "Tipo de comprobante.",
        },
        "letra": {"type": "string", "enum": ["A", "B", "C", "E", "M", ""],
                  "description": "Letra del comprobante."},
        "punto_venta": {"type": "string", "description": "Punto de venta, 4 digitos."},
        "numero": {"type": "string", "description": "Numero del comprobante, 8 digitos."},
        "fecha_emision": {"type": "string", "description": "Fecha de emision, dd/mm/aaaa."},
        "periodo": {"type": "string", "description": "Periodo facturado si figura."},
        "cuit_emisor": {"type": "string", "description": "CUIT de quien emite, solo digitos."},
        "razon_social_emisor": {"type": "string"},
        "cuit_receptor": {"type": "string", "description": "CUIT de quien recibe, solo digitos."},
        "razon_social_receptor": {"type": "string"},
        "moneda": {"type": "string", "enum": ["ARS", "USD", "EUR", "BRL"]},
        "tipo_cambio": {"type": "string", "description": "Cotizacion si la factura no esta en pesos, si no '0'."},
        "gravado_21": {"type": "string", "description": "Neto gravado al 21%."},
        "gravado_105": {"type": "string", "description": "Neto gravado al 10,5%."},
        "iva_21": {"type": "string"},
        "iva_105": {"type": "string"},
        "iva_27": {"type": "string"},
        "no_gravado": {"type": "string", "description": "Importe neto no gravado o no computable."},
        "exento": {"type": "string", "description": "Importe exento."},
        "percepcion_iibb": {"type": "string", "description": "Percepcion de Ingresos Brutos."},
        "otros_tributos": {"type": "string"},
        "total": {"type": "string", "description": "Importe total del comprobante."},
        "referencia": {"type": "string", "description": "File, legajo, reserva o numero de negocio."},
        "pasajeros": {"type": "string", "description": "Nombre de los pasajeros si figura."},
        "cae": {"type": "string", "description": "CAE, 14 digitos."},
        "vencimiento_cae": {"type": "string"},
        "conceptos": {
            "type": "array",
            "description": "Lineas del detalle.",
            "items": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string"},
                    "descripcion": {"type": "string"},
                    "importe": {"type": "string"},
                },
                "required": ["codigo", "descripcion", "importe"],
                "additionalProperties": False,
            },
        },
        "observaciones": {
            "type": "string",
            "description": "Que no se pudo leer con certeza, o esta vacio si se leyo todo.",
        },
    },
    "required": [
        "clase", "letra", "punto_venta", "numero", "fecha_emision", "periodo",
        "cuit_emisor", "razon_social_emisor", "cuit_receptor", "razon_social_receptor",
        "moneda", "tipo_cambio", "gravado_21", "gravado_105", "iva_21", "iva_105",
        "iva_27", "no_gravado", "exento", "percepcion_iibb", "otros_tributos",
        "total", "referencia", "pasajeros", "cae", "vencimiento_cae", "conceptos",
        "observaciones",
    ],
    "additionalProperties": False,
}

INSTRUCCIONES = """Sos un asistente que transcribe facturas argentinas para una agencia de viajes.

Tu unica tarea es COPIAR los importes tal como figuran en el comprobante. No
calcules, no estimes, no completes lo que no veas.

Reglas:

1. Los importes vienen en formato argentino: 1.234.567,89 son un millon
   doscientos treinta y cuatro mil. El punto separa miles y la coma, decimales.
   Devolvelos siempre como numero con punto decimal: "1234567.89".

2. Si un campo no figura en la factura, devolve "0" para los importes y ""
   para los textos. NUNCA inventes ni deduzcas un valor que no este impreso.

3. Distingui bien estas categorias, que suelen estar en el pie:
   - gravado_21 / gravado_105: el neto sobre el que se calcula el IVA.
   - iva_21 / iva_105: el impuesto en si.
   - exento: operaciones exentas, tipicamente el transporte internacional.
   - no_gravado: lo que esta fuera del objeto del impuesto. Algunos
     mayoristas lo llaman "no computable" o "servicios no gravados".
   - percepcion_iibb: percepcion de Ingresos Brutos.
   El pie puede venir en columnas: fijate bien que importe corresponde a que
   etiqueta, alineando por posicion.

4. El CAE tiene 14 digitos y NO es un importe. Los numeros de reserva o file
   tampoco.

5. Si la factura esta en dolares, buscá el tipo de cambio: suele aparecer como
   "Tipo de Cambio", "al cambio" o "U$1,00=$1.512,00".

6. En observaciones, escribi que no pudiste leer con certeza: si un numero esta
   borroso, cortado o ambiguo, decilo. Es preferible que avises antes que
   arriesgar un digito. Si leiste todo con claridad, dejalo vacio."""


def leer_con_ia(
    ruta: str | Path,
    cuit_agencia: str = "",
    modelo: str | None = None,
    cliente=None,
) -> Comprobante:
    """Lee una factura con un modelo de vision y la devuelve ya validada."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorDeIA(f"No existe el archivo {ruta}")

    tamano = ruta.stat().st_size
    if tamano > LIMITE_MB * 1024 * 1024:
        raise ErrorDeIA(
            f"{ruta.name} pesa {tamano / 1024 / 1024:.1f} MB y el limite para "
            f"mandarlo al modelo es {LIMITE_MB} MB. Si son varias facturas en un "
            "mismo archivo, separalas."
        )

    cliente = cliente or _cliente()
    modelo = modelo or modelo_configurado()

    respuesta = _pedir(cliente, modelo, ruta)
    datos = _extraer_json(respuesta)
    comprobante = _a_comprobante(datos, ruta.name, cuit_agencia)

    comprobante.motor_pdf = f"ia:{modelo}"
    # Lo que devuelve el modelo pasa por el mismo control que el parser.
    _controlar(comprobante)
    comprobante.avisos.insert(
        0,
        "Esta factura la leyo un modelo de lenguaje, no el lector de reglas. "
        "Revisa los importes contra el comprobante antes de liquidar.",
    )
    if datos.get("observaciones"):
        comprobante.avisos.append(f"El modelo avisa: {datos['observaciones']}")
        comprobante.confiable = False
    return comprobante


def _cliente():
    try:
        import anthropic
    except ImportError as exc:
        raise ErrorDeIA(
            "Para leer facturas con IA hace falta la libreria de Anthropic:\n"
            "    pip install anthropic"
        ) from exc

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise ErrorDeIA(
            "Falta la credencial para usar el modelo.\n"
            "Consegui una clave en https://console.anthropic.com y cargala en la\n"
            "variable de entorno ANTHROPIC_API_KEY.\n"
            "En Vercel se carga en Settings -> Environment Variables."
        )
    return anthropic.Anthropic()


def _pedir(cliente, modelo: str, ruta: Path):
    contenido = base64.standard_b64encode(ruta.read_bytes()).decode("utf-8")
    documento = {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": contenido,
        },
    }

    try:
        return cliente.messages.create(
            model=modelo,
            max_tokens=MAX_TOKENS,
            system=INSTRUCCIONES,
            messages=[
                {
                    "role": "user",
                    "content": [
                        documento,
                        {"type": "text", "text": "Transcribi los datos de esta factura."},
                    ],
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": ESQUEMA}},
        )
    except Exception as exc:
        raise ErrorDeIA(_mensaje_de_error(exc)) from exc


def _mensaje_de_error(exc: Exception) -> str:
    nombre = type(exc).__name__
    if "Authentication" in nombre:
        return "La credencial del modelo no es valida. Revisa ANTHROPIC_API_KEY."
    if "RateLimit" in nombre:
        return "El modelo esta recibiendo demasiadas consultas. Esperá un momento y reintentá."
    if "Connection" in nombre or "Timeout" in nombre:
        return "No se pudo conectar con el modelo. Revisa la conexion a internet."
    if "BadRequest" in nombre:
        return f"El modelo rechazo el archivo: {exc}"
    return f"Fallo la lectura con IA ({nombre}): {exc}"


def _extraer_json(respuesta) -> dict:
    if getattr(respuesta, "stop_reason", None) == "refusal":
        raise ErrorDeIA("El modelo no quiso procesar el archivo.")

    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "text":
            try:
                return json.loads(bloque.text)
            except json.JSONDecodeError as exc:
                raise ErrorDeIA(f"El modelo devolvio algo que no es JSON: {exc}") from exc
    raise ErrorDeIA("El modelo no devolvio ningun dato.")


def _a_comprobante(datos: dict, archivo: str, cuit_agencia: str) -> Comprobante:
    def texto(clave: str) -> str:
        return str(datos.get(clave) or "").strip()

    def importe(clave: str) -> Decimal:
        return dec(str(datos.get(clave) or "0").replace(" ", ""), CERO)

    comprobante = Comprobante(
        archivo=archivo,
        clase=texto("clase") or "FACTURA",
        letra=texto("letra"),
        punto_venta=texto("punto_venta").zfill(4) if texto("punto_venta") else "",
        numero=texto("numero").zfill(8) if texto("numero") else "",
        fecha_emision=texto("fecha_emision"),
        periodo=texto("periodo"),
        cuit_emisor=_solo_digitos(texto("cuit_emisor")),
        razon_social_emisor=texto("razon_social_emisor"),
        cuit_receptor=_solo_digitos(texto("cuit_receptor")),
        razon_social_receptor=texto("razon_social_receptor"),
        moneda=texto("moneda") or "ARS",
        tipo_cambio=importe("tipo_cambio"),
        gravado_21=importe("gravado_21"),
        gravado_105=importe("gravado_105"),
        iva_21=importe("iva_21"),
        iva_105=importe("iva_105"),
        iva_27=importe("iva_27"),
        no_gravado=importe("no_gravado"),
        exento=importe("exento"),
        percepcion_iibb=importe("percepcion_iibb"),
        otros_tributos=importe("otros_tributos"),
        total=importe("total"),
        referencia=texto("referencia"),
        pasajeros=texto("pasajeros"),
        cae=_solo_digitos(texto("cae")),
        vencimiento_cae=texto("vencimiento_cae"),
    )

    for concepto in datos.get("conceptos") or []:
        if not isinstance(concepto, dict):
            continue
        comprobante.conceptos.append(
            ConceptoFactura(
                codigo=str(concepto.get("codigo") or "").strip(),
                descripcion=str(concepto.get("descripcion") or "").strip(),
                importe=dec(str(concepto.get("importe") or "0"), CERO),
            )
        )

    _decidir_sentido(comprobante, cuit_agencia)
    return comprobante


def _solo_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _decidir_sentido(comprobante: Comprobante, cuit_agencia: str) -> None:
    agencia = _solo_digitos(cuit_agencia)
    if not agencia:
        comprobante.sentido = COMPRA
        return
    if comprobante.cuit_emisor == agencia:
        comprobante.sentido = VENTA
    elif comprobante.cuit_receptor == agencia:
        comprobante.sentido = COMPRA
    else:
        comprobante.sentido = COMPRA
        comprobante.avisos.append(
            f"El CUIT de la agencia ({cuit_agencia}) no figura en el comprobante: "
            "revisa que la factura sea de esta agencia."
        )

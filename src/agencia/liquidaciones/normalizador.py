"""Traduce una tabla cruda a lineas de liquidacion.

Cada mayorista arma la planilla a su manera. En lugar de exigir un formato,
el normalizador reconoce los encabezados por sinonimos y deja registro de que
columna interpreto como que, para que el operador pueda auditarlo.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any, Iterable

from ..dinero import CERO, dec, redondear
from ..dominio import Moneda
from .modelos import LineaLiquidacion

# Sinonimos por campo. El orden no importa: gana el mas especifico.
SINONIMOS: dict[str, list[str]] = {
    "referencia": [
        "file", "nro file", "n file", "numero de file", "expediente", "reserva",
        "nro reserva", "n reserva", "numero de reserva", "localizador", "voucher",
        "legajo", "operacion", "nro operacion", "comprobante", "orden", "booking",
        "pnr", "id",
    ],
    "fecha": [
        "fecha", "fecha emision", "f emision", "fecha de emision", "fecha venta",
        "fecha de venta", "emision", "fecha operacion",
    ],
    "pasajero": [
        "pasajero", "pasajeros", "pax", "titular", "apellido y nombre",
        "nombre del pasajero", "nombre pasajero", "cliente",
    ],
    "destino": ["destino", "ciudad", "ruta", "itinerario", "tramo", "origen destino"],
    "proveedor": [
        "proveedor", "operador", "prestador", "aerolinea", "linea aerea", "cia",
        "compania", "hotel", "mayorista",
    ],
    "servicio_descripcion": [
        "servicio", "concepto", "descripcion", "detalle", "producto", "rubro",
        "tipo de servicio", "tipo servicio", "prestacion",
    ],
    "moneda": ["moneda", "mon", "divisa", "cur", "currency"],
    "tipo_cambio": [
        "tc", "t c", "tipo de cambio", "tipo cambio", "cotizacion", "cambio",
        "paridad", "tc aplicado",
    ],
    "importe_total": [
        "total", "importe total", "importe", "venta", "precio venta",
        "precio de venta", "tarifa", "pvp", "total venta", "monto",
        "total servicio", "bruto",
    ],
    "costo_neto": [
        "neto", "costo", "importe neto", "neto proveedor", "costo neto",
        "a pagar proveedor", "tarifa neta", "neto operador",
    ],
    "comision": [
        "comision", "comisiones", "com", "comision agencia", "comision neta",
        "comision sin iva", "com agencia", "comision s iva",
    ],
    "iva_comision": [
        "iva comision", "iva com", "iva s comision", "iva sobre comision",
        "iva 21", "iva 21 comision", "iva de la comision", "iva",
    ],
    "over": ["over", "markup", "mark up", "sobreprecio", "plus", "adicional agencia"],
    "ret_ganancias": [
        "ret ganancias", "retencion ganancias", "ret gcias", "rg 830", "ganancias",
        "ret imp ganancias", "retencion de ganancias",
    ],
    "ret_iva": [
        "ret iva", "retencion iva", "rg 2854", "ret imp iva", "retencion de iva",
    ],
    "ret_iibb": [
        "ret iibb", "retencion iibb", "ingresos brutos", "iibb", "sircar",
        "ret ingresos brutos", "retencion ingresos brutos", "ret ib",
    ],
    "otros_descuentos": [
        "otros descuentos", "descuentos", "ajustes", "notas de credito", "gastos",
        "otros",
    ],
    "neto_a_cobrar": [
        "neto a cobrar", "a cobrar", "saldo", "liquido", "neto a pagar",
        "total a pagar", "importe a cobrar", "saldo a favor", "liquidado",
        "neto liquidado",
    ],
}

CAMPOS_TEXTO = {
    "referencia", "fecha", "pasajero", "destino", "proveedor",
    "servicio_descripcion", "moneda",
}

# Palabras clave para inferir el tipo de servicio desde la descripcion.
REGLAS_SERVICIO: list[tuple[str, tuple[str, ...]]] = [
    ("AEREO_INTERNACIONAL", ("aereo internacional", "vuelo internacional", "intl", "internacional aereo")),
    ("AEREO_CABOTAJE", ("cabotaje", "aereo nacional", "vuelo nacional", "domestico")),
    ("AEREO_INTERNACIONAL", ("aereo", "vuelo", "pasaje aereo", "ticket", "boleto aereo", "air")),
    ("HOTELERIA_EXTERIOR", ("hotel exterior", "alojamiento exterior", "hotel internacional")),
    ("HOTELERIA_NACIONAL", ("hotel nacional", "alojamiento nacional", "hoteleria nacional")),
    ("HOTELERIA_EXTERIOR", ("hotel", "hoteleria", "alojamiento", "hospedaje", "apart")),
    ("PAQUETE_EXTERIOR", ("paquete exterior", "paquete internacional")),
    ("PAQUETE_NACIONAL", ("paquete nacional", "paquete argentina")),
    ("PAQUETE_EXTERIOR", ("paquete", "circuito", "tour", "programa")),
    ("CRUCERO", ("crucero", "cruise", "naviera")),
    ("ASISTENCIA_VIAJERO", ("asistencia", "assist", "cobertura medica", "asistencia al viajero")),
    ("SEGURO", ("seguro", "poliza", "cancelacion")),
    ("ALQUILER_AUTO_EXTERIOR", ("rent a car", "alquiler de auto", "alquiler auto", "rentacar", "car")),
    ("TERRESTRE_LARGA_DISTANCIA", ("bus", "omnibus", "micro", "terrestre", "colectivo")),
    ("TREN_O_BUS_EXTERIOR", ("tren", "eurail", "rail")),
    ("EXCURSION_EXTERIOR", ("excursion", "traslado", "transfer", "entrada", "ticket atraccion")),
    ("FEE_AGENCIA", ("fee", "cargo por gestion", "gastos administrativos", "service charge")),
]

# Las claves se comparan ya normalizadas: "U$S" llega como "u s".
MONEDAS = {
    "ars": Moneda.ARS, "peso": Moneda.ARS, "pesos": Moneda.ARS, "ar": Moneda.ARS,
    "usd": Moneda.USD, "u s": Moneda.USD, "us": Moneda.USD, "dolar": Moneda.USD,
    "dolares": Moneda.USD, "dol": Moneda.USD,
    "eur": Moneda.EUR, "euro": Moneda.EUR, "euros": Moneda.EUR,
    "brl": Moneda.BRL, "real": Moneda.BRL, "reales": Moneda.BRL,
}


def normalizar_texto(texto: Any) -> str:
    """minusculas, sin tildes, sin puntuacion, espacios colapsados."""
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def detectar_columnas(
    encabezados: Iterable[str], mapeo_manual: dict[str, str] | None = None
) -> tuple[dict[int, str], list[str]]:
    """Asocia cada columna del archivo con un campo del modelo.

    Devuelve ({indice_columna: campo}, [encabezados no reconocidos]).
    El mapeo manual del perfil del mayorista tiene prioridad absoluta.
    """
    encabezados = list(encabezados)
    manual = {normalizar_texto(k): v for k, v in (mapeo_manual or {}).items()}

    candidatos: list[tuple[int, str, int]] = []  # (columna, campo, puntaje)
    sin_reconocer: list[str] = []

    for indice, bruto in enumerate(encabezados):
        titulo = normalizar_texto(bruto)
        if not titulo:
            continue
        if titulo in manual:
            candidatos.append((indice, manual[titulo], 10_000))
            continue
        mejor = _mejor_campo(titulo)
        if mejor:
            campo, puntaje = mejor
            candidatos.append((indice, campo, puntaje))
        else:
            sin_reconocer.append(str(bruto))

    # Si dos columnas reclaman el mismo campo, gana la de mayor puntaje.
    asignado: dict[str, tuple[int, int]] = {}
    for indice, campo, puntaje in candidatos:
        actual = asignado.get(campo)
        if actual is None or puntaje > actual[1]:
            if actual is not None:
                sin_reconocer.append(str(encabezados[actual[0]]))
            asignado[campo] = (indice, puntaje)
        else:
            sin_reconocer.append(str(encabezados[indice]))

    columnas = {indice: campo for campo, (indice, _) in asignado.items()}
    return columnas, sin_reconocer


def _mejor_campo(titulo: str) -> tuple[str, int] | None:
    """Elige el campo cuyo sinonimo describe mejor al encabezado."""
    mejor: tuple[str, int] | None = None
    for campo, sinonimos in SINONIMOS.items():
        for sinonimo in sinonimos:
            if titulo == sinonimo:
                puntaje = 1000 + len(sinonimo)
            elif _contiene_palabras(titulo, sinonimo):
                puntaje = len(sinonimo)
            else:
                continue
            if mejor is None or puntaje > mejor[1]:
                mejor = (campo, puntaje)
    return mejor


def _contiene_palabras(titulo: str, sinonimo: str) -> bool:
    """Coincidencia por palabras completas, para que 'com' no matchee 'compania'."""
    palabras_titulo = titulo.split()
    palabras_sinonimo = sinonimo.split()
    n = len(palabras_sinonimo)
    return any(
        palabras_titulo[i : i + n] == palabras_sinonimo
        for i in range(len(palabras_titulo) - n + 1)
    )


def inferir_tipo_servicio(
    texto: str, mapeo: dict[str, str] | None = None, default: str = "OTRO"
) -> str:
    """Deduce el tipo de servicio fiscal a partir de la descripcion."""
    normalizado = normalizar_texto(texto)
    if not normalizado:
        return default

    for clave, destino in (mapeo or {}).items():
        if normalizar_texto(clave) in normalizado:
            return destino

    for tipo, patrones in REGLAS_SERVICIO:
        if any(_contiene_palabras(normalizado, normalizar_texto(p)) for p in patrones):
            return tipo
    return default


def inferir_moneda(texto: Any, default: Moneda = Moneda.ARS) -> Moneda:
    normalizado = normalizar_texto(texto)
    if not normalizado:
        return default
    if normalizado in MONEDAS:
        return MONEDAS[normalizado]
    for clave, moneda in MONEDAS.items():
        if _contiene_palabras(normalizado, clave):
            return moneda
    return default


def fila_a_linea(
    fila: list[Any],
    columnas: dict[int, str],
    numero_fila: int,
    perfil: dict[str, Any] | None = None,
) -> LineaLiquidacion | None:
    """Arma una LineaLiquidacion a partir de una fila cruda."""
    perfil = perfil or {}
    datos: dict[str, Any] = {}
    crudo: dict[str, Any] = {}

    for indice, campo in columnas.items():
        if indice >= len(fila):
            continue
        valor = fila[indice]
        crudo[campo] = valor
        if campo in CAMPOS_TEXTO:
            datos[campo] = str(valor).strip() if valor is not None else ""
        else:
            datos[campo] = dec(valor, default=CERO)

    if _fila_vacia(datos):
        return None

    moneda = inferir_moneda(datos.pop("moneda", ""), Moneda(perfil.get("moneda_default", "ARS")))

    descripcion = " ".join(
        str(datos.get(c, "")) for c in ("servicio_descripcion", "destino", "proveedor")
    ).strip()
    tipo_servicio = inferir_tipo_servicio(
        descripcion,
        perfil.get("mapeo_servicios"),
        perfil.get("tipo_servicio_default", "OTRO"),
    )

    linea = LineaLiquidacion(
        tipo_servicio=tipo_servicio,
        moneda=moneda,
        fila=numero_fila,
        crudo=crudo,
        **datos,
    )
    _completar_derivados(linea)
    return linea


def _fila_vacia(datos: dict[str, Any]) -> bool:
    """Descarta filas de separacion y subtotales sin contenido util."""
    hay_texto = any(
        str(v).strip() for k, v in datos.items() if k in CAMPOS_TEXTO and k != "moneda"
    )
    hay_importe = any(
        dec(v, CERO) != CERO for k, v in datos.items() if k not in CAMPOS_TEXTO
    )
    return not hay_texto and not hay_importe


def _completar_derivados(linea: LineaLiquidacion) -> None:
    """Rellena lo que la planilla no trajo pero se puede deducir."""
    if linea.costo_neto == CERO and linea.importe_total != CERO and linea.comision != CERO:
        linea.costo_neto = redondear(linea.importe_total - linea.comision)
        linea.avisos.append("Costo neto deducido como importe total menos comision.")
    elif linea.importe_total == CERO and linea.costo_neto != CERO:
        linea.importe_total = redondear(linea.costo_neto + linea.comision)
        linea.avisos.append("Importe total deducido como costo neto mas comision.")

    if linea.neto_a_cobrar == CERO and linea.comision != CERO:
        linea.neto_a_cobrar = redondear(
            linea.comision
            + linea.iva_comision
            - linea.ret_ganancias
            - linea.ret_iva
            - linea.ret_iibb
            - linea.otros_descuentos
        )
        linea.avisos.append("Neto a cobrar calculado a partir de comision y retenciones.")

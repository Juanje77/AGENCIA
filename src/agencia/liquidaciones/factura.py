"""Lectura de facturas de mayoristas de turismo en PDF.

Cada mayorista arma la factura a su manera. Sobre los archivos reales de la
agencia se reconocen tres disposiciones distintas del pie de totales:

  * vertical, una etiqueta y su importe por renglon
    ("Importe Neto Gravado AR$ 1.080.749,58");
  * horizontal, un renglon de etiquetas y el siguiente con los importes
    alineados por columna ("Exento  No Gravado  Gravado 21% ...");
  * en pares sobre el mismo renglon ("Gravado 21%: 84.11  Iva 21%: 17.66").

El parser prueba las tres y despues controla que los importes cierren contra
el total, que es la unica forma de saber si leyo bien.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from ..dinero import CERO, dec, redondear
from .lectores.base import ErrorDeLectura
from .lectores.pdf_texto import DocumentoPDF, Palabra, extraer

IMPORTE = r"-?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|-?\d+,\d{1,2}|-?\d+\.\d{1,2}|-?\d+"
CUIT = r"\b(\d{2}[-\s]?\d{8}[-\s]?\d)\b"
FECHA = r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"

TIPOS_COMPROBANTE = {
    "01": ("FACTURA", "A"), "02": ("NOTA DE DEBITO", "A"), "03": ("NOTA DE CREDITO", "A"),
    "06": ("FACTURA", "B"), "07": ("NOTA DE DEBITO", "B"), "08": ("NOTA DE CREDITO", "B"),
    "11": ("FACTURA", "C"), "12": ("NOTA DE DEBITO", "C"), "13": ("NOTA DE CREDITO", "C"),
    "19": ("FACTURA", "E"), "20": ("NOTA DE DEBITO", "E"), "21": ("NOTA DE CREDITO", "E"),
    "51": ("FACTURA", "M"), "52": ("NOTA DE DEBITO", "M"), "53": ("NOTA DE CREDITO", "M"),
    "201": ("FACTURA DE CREDITO", "A"), "203": ("NOTA DE CREDITO", "A"),
}
CLASES_NEGATIVAS = ("NOTA DE CREDITO",)

VENTA, COMPRA = "VENTA", "COMPRA"


def _sin_tildes(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _num(texto: str) -> Decimal:
    """Interpreta un importe de factura, tolerando el ruido del OCR."""
    limpio = re.sub(r"[^\d.,\-]", "", str(texto))
    return dec(limpio, CERO) if limpio else CERO


@dataclass
class ConceptoFactura:
    codigo: str = ""
    descripcion: str = ""
    cantidad: Decimal = CERO
    importe: Decimal = CERO
    alicuota_iva: Decimal | None = None
    iva: Decimal = CERO

    def a_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "descripcion": self.descripcion,
            "cantidad": str(self.cantidad),
            "importe": str(self.importe),
            "alicuota_iva": str(self.alicuota_iva) if self.alicuota_iva is not None else None,
            "iva": str(self.iva),
        }


@dataclass
class Comprobante:
    archivo: str = ""
    clase: str = ""
    letra: str = ""
    punto_venta: str = ""
    numero: str = ""
    fecha_emision: str = ""
    periodo: str = ""
    vencimiento: str = ""

    cuit_emisor: str = ""
    razon_social_emisor: str = ""
    cuit_receptor: str = ""
    razon_social_receptor: str = ""
    sentido: str = COMPRA
    """COMPRA cuando el mayorista le factura a la agencia; VENTA al reves."""

    moneda: str = "ARS"
    tipo_cambio: Decimal = CERO

    gravado_21: Decimal = CERO
    gravado_105: Decimal = CERO
    neto_gravado_informado: Decimal = CERO
    iva_21: Decimal = CERO
    iva_105: Decimal = CERO
    iva_27: Decimal = CERO
    no_gravado: Decimal = CERO
    exento: Decimal = CERO
    otros_tributos: Decimal = CERO
    percepcion_iibb: Decimal = CERO
    percepcion_iva: Decimal = CERO
    total: Decimal = CERO

    referencia: str = ""
    """File, legajo o numero de negocio del mayorista."""
    pasajeros: str = ""
    cae: str = ""
    vencimiento_cae: str = ""

    conceptos: list[ConceptoFactura] = field(default_factory=list)
    deducido: bool = False
    """Marca que algun importe se infirio en vez de leerse."""
    motor_pdf: str = ""
    avisos: list[str] = field(default_factory=list)
    confiable: bool = True

    # --- derivados --------------------------------------------------------

    @property
    def identificacion(self) -> str:
        numero = f"{self.punto_venta}-{self.numero}" if self.punto_venta else self.numero
        return " ".join(p for p in (self.clase, self.letra, numero) if p)

    @property
    def signo(self) -> int:
        return -1 if self.clase in CLASES_NEGATIVAS else 1

    @property
    def iva_total(self) -> Decimal:
        return redondear(self.iva_21 + self.iva_105 + self.iva_27)

    @property
    def neto_gravado(self) -> Decimal:
        return redondear(self.gravado_21 + self.gravado_105)

    @property
    def comisionable(self) -> Decimal:
        """Lo que el mayorista reconoce como base de comision.

        Es el servicio en si: lo gravado mas lo exento. Las tasas, los cargos y
        los impuestos que van como no gravados no suelen pagar comision.
        """
        return redondear(self.neto_gravado + self.exento)

    @property
    def no_comisionable(self) -> Decimal:
        return redondear(self.no_gravado + self.otros_tributos)

    @property
    def total_calculado(self) -> Decimal:
        return redondear(
            self.neto_gravado + self.iva_total + self.no_gravado
            + self.exento + self.otros_tributos
        )

    @property
    def credito_fiscal(self) -> Decimal:
        """IVA computable: solo el discriminado de una factura de compra A o M."""
        if self.sentido != COMPRA or self.letra not in ("A", "M"):
            return CERO
        return self.iva_total

    def a_dict(self) -> dict:
        return {
            "archivo": self.archivo,
            "identificacion": self.identificacion,
            "clase": self.clase,
            "letra": self.letra,
            "punto_venta": self.punto_venta,
            "numero": self.numero,
            "fecha_emision": self.fecha_emision,
            "periodo": self.periodo,
            "cuit_emisor": self.cuit_emisor,
            "razon_social_emisor": self.razon_social_emisor,
            "cuit_receptor": self.cuit_receptor,
            "razon_social_receptor": self.razon_social_receptor,
            "sentido": self.sentido,
            "moneda": self.moneda,
            "tipo_cambio": str(self.tipo_cambio),
            "gravado_21": str(self.gravado_21),
            "gravado_105": str(self.gravado_105),
            "neto_gravado": str(self.neto_gravado),
            "iva_21": str(self.iva_21),
            "iva_105": str(self.iva_105),
            "iva_27": str(self.iva_27),
            "iva_total": str(self.iva_total),
            "no_gravado": str(self.no_gravado),
            "exento": str(self.exento),
            "otros_tributos": str(self.otros_tributos),
            "percepcion_iibb": str(self.percepcion_iibb),
            "total": str(self.total),
            "comisionable": str(self.comisionable),
            "no_comisionable": str(self.no_comisionable),
            "credito_fiscal": str(self.credito_fiscal),
            "referencia": self.referencia,
            "pasajeros": self.pasajeros,
            "cae": self.cae,
            "vencimiento_cae": self.vencimiento_cae,
            "conceptos": [c.a_dict() for c in self.conceptos],
            "motor_pdf": self.motor_pdf,
            "confiable": self.confiable,
            "avisos": self.avisos,
        }


def leer_factura(ruta: str | Path, cuit_agencia: str = "") -> Comprobante:
    documento = extraer(ruta)
    comprobante = parsear(documento, Path(ruta).name, cuit_agencia)
    comprobante.motor_pdf = documento.motor
    comprobante.avisos.extend(documento.avisos)
    return comprobante


def parsear(
    documento: DocumentoPDF, archivo: str = "", cuit_agencia: str = ""
) -> Comprobante:
    renglones = _renglones_unicos(documento)
    lineas = [" ".join(p.texto for p in sorted(r, key=lambda p: p.x)) for r in renglones]
    lineas = [_sin_tildes(l) for l in lineas]
    texto = "\n".join(lineas)

    c = Comprobante(archivo=archivo)
    _encabezado(c, texto)
    _partes(c, texto, lineas, cuit_agencia)
    _moneda(c, texto)
    _totales(c, lineas, renglones)
    _conceptos(c, lineas)
    _referencias(c, texto)
    _controlar(c)

    if c.total == CERO and c.neto_gravado == CERO and not c.conceptos:
        raise ErrorDeLectura(
            f"El PDF {archivo} no parece una factura: no se encontraron importes. "
            "Si el archivo es una planilla, guardalo como CSV o Excel."
        )
    return c


def _renglones_unicos(documento: DocumentoPDF) -> list[list[Palabra]]:
    """Descarta las paginas repetidas (original, duplicado y triplicado)."""
    vistos: set[str] = set()
    salida: list[list[Palabra]] = []
    for pagina in documento.paginas:
        for renglon in pagina.renglones or []:
            clave = " ".join(p.texto for p in sorted(renglon, key=lambda p: p.x)).strip()
            if not clave:
                continue
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append(renglon)
    if salida:
        return salida
    # Sin posiciones (por ejemplo con PyPDF2) se trabaja sobre el texto plano.
    return [
        [Palabra(texto=linea, x=0.0, y=float(i))]
        for i, linea in enumerate(documento.texto.splitlines())
        if linea.strip()
    ]


# --- encabezado --------------------------------------------------------------

def _encabezado(c: Comprobante, texto: str) -> None:
    codigo = re.search(r"C[oO]d(?:igo)?\.?\s*:?\s*(\d{1,3})\b", texto, re.I)
    if codigo:
        clave = codigo.group(1).lstrip("0") or "0"
        clave = clave.zfill(2) if len(clave) <= 2 else clave
        if clave in TIPOS_COMPROBANTE:
            c.clase, c.letra = TIPOS_COMPROBANTE[clave]

    if not c.clase:
        for patron, clase in (
            (r"NOTA\s+DE\s+CR[EE]DITO", "NOTA DE CREDITO"),
            (r"NOTA\s+DE\s+D[EE]BITO", "NOTA DE DEBITO"),
            (r"FACTURA\s+DE\s+CR[EE]DITO|FCE", "FACTURA DE CREDITO"),
            (r"FACTURA", "FACTURA"),
            (r"LIQUIDACION", "LIQUIDACION"),
        ):
            if re.search(patron, texto, re.I):
                c.clase = clase
                break

    # Numero: "0022-00443515", "FCE-0025-A-00230365" o "Punto de Venta / Comp. Nro".
    numero = re.search(r"\b(?:FCE|FA|NC|ND)?-?(\d{4,5})\s*-\s*([ABCEM4])?\s*-?\s*(\d{7,8})\b", texto)
    if numero:
        c.punto_venta = numero.group(1).zfill(4)
        c.numero = numero.group(3).zfill(8)
        if numero.group(2) and numero.group(2) in "ABCEM":
            c.letra = c.letra or numero.group(2)
    else:
        punto = re.search(r"Punto\s+de\s+Venta:?\s*(\d{1,5})", texto, re.I)
        if punto:
            c.punto_venta = punto.group(1).zfill(4)
        suelto = re.search(
            r"(?:Comp\.?\s*(?:Nro|N[oº°]?)|Factura|Nro\.?)\s*:?\s*(\d{6,8})\b", texto, re.I
        )
        if suelto:
            c.numero = suelto.group(1).zfill(8)

    if not c.letra:
        letra = re.search(r"(?:^|\n)\s*([ABCEM])\s*(?:\n|$)", texto)
        if letra:
            c.letra = letra.group(1)

    fecha = re.search(
        rf"Fecha\s*(?:de\s*)?Emisi[oó]n\s*:?\s*{FECHA}|FECHA\s*:?\s*{FECHA}", texto, re.I
    )
    if fecha:
        c.fecha_emision = fecha.group(1) or fecha.group(2)

    periodo = re.search(
        rf"(?:Desde|Periodo\s+Facturado\s+Desde)\s*:?\s*{FECHA}\s*(?:-\s*Hasta\s*:?\s*|al\s*){FECHA}",
        texto, re.I,
    )
    if periodo:
        c.periodo = f"{periodo.group(1)} al {periodo.group(2)}"

    vence = re.search(
        rf"(?:Fecha\s+de\s+Vto|Vencimiento(?:\s+de\s+pago)?)\s*:?\s*{FECHA}", texto, re.I
    )
    if vence:
        c.vencimiento = vence.group(1)

    cae = re.search(r"CAE\s*(?:N[oº°ro.]*)?\s*:?\s*(\d{14})", texto, re.I)
    if cae:
        c.cae = cae.group(1)
    vto_cae = re.search(rf"(?:Vto\.?|Vencimiento)\s*(?:de\s*)?CAE\s*:?\s*{FECHA}", texto, re.I)
    if vto_cae:
        c.vencimiento_cae = vto_cae.group(1)


def _partes(c: Comprobante, texto: str, lineas: list[str], cuit_agencia: str) -> None:
    cuits: list[str] = []
    # El OCR a veces rompe "C.U.I.T."; se buscan los numeros de 11 digitos.
    for encontrado in re.findall(r"\b(\d{2}[-\s]?\d{8}[-\s]?\d)\b", texto):
        normalizado = re.sub(r"[-\s]", "", encontrado)
        if normalizado not in cuits:
            cuits.append(normalizado)

    agencia = re.sub(r"[-\s]", "", cuit_agencia) if cuit_agencia else ""

    if agencia and agencia in cuits:
        otros = [x for x in cuits if x != agencia]
        emisor = cuits[0]
        if emisor == agencia:
            c.sentido = VENTA
            c.cuit_emisor, c.cuit_receptor = agencia, (otros[0] if otros else "")
        else:
            c.sentido = COMPRA
            c.cuit_emisor, c.cuit_receptor = emisor, agencia
    else:
        c.cuit_emisor = cuits[0] if cuits else ""
        c.cuit_receptor = cuits[1] if len(cuits) > 1 else ""
        c.sentido = COMPRA
        if agencia:
            c.avisos.append(
                f"El CUIT de la agencia ({cuit_agencia}) no figura en el comprobante: "
                "revisa que la factura sea de esta agencia."
            )

    # Razon social del emisor: la linea mas prominente antes de los datos fiscales.
    for linea in lineas[:12]:
        limpia = linea.strip()
        if re.search(
            r"\b(S\.?A\.?|S\.?R\.?L\.?|SRL|SAS|S\.?A\.?S\.?|MAYORISTA|OPERADOR|TRAVEL|TURISMO)\b",
            limpia, re.I,
        ):
            limpia = re.sub(
                r"^(?:Razon\s+Social|Sr\.?/Sres\.?|Senor(?:es)?)\s*:?\s*", "",
                limpia, flags=re.I,
            )
            candidata = re.split(
                r"\s{2,}|FECHA|C\.?U\.?I\.?T|Factura|Vencimiento|Ing\.?\s*Brutos|Direccion",
                limpia, flags=re.I,
            )[0].strip()
            if len(candidata) > 3:
                c.razon_social_emisor = candidata
                break

    cliente = re.search(
        r"(?:Cliente|Sr\.?/Sres\.?|Senor(?:es)?|Razon\s+Social)\s*:?\s*([A-ZÑ][^\n]{3,60})",
        texto, re.I,
    )
    if cliente:
        c.razon_social_receptor = re.split(
            r"\s{2,}|File|CUIT|C\.U\.I\.T", cliente.group(1)
        )[0].strip()


def _moneda(c: Comprobante, texto: str) -> None:
    if re.search(r"Moneda\s*:?\s*(?:USD|DOL|U\$S)", texto, re.I) or re.search(
        r"TOTAL\s+USD", texto, re.I
    ):
        c.moneda = "USD"
    elif re.search(r"Moneda\s*:?\s*(?:EUR)", texto, re.I):
        c.moneda = "EUR"

    for patron in (
        r"Tipo\s+de\s+Cambio\s*:?\s*(\d[\d.,]*)",
        r"AL\s+CAMBIO\s+(\d[\d.,]*)",
        r"U\$?\s*1[.,]00\s*=\s*\$?\s*(\d[\d.,]*)",
    ):
        encontrado = re.search(patron, texto, re.I)
        if encontrado:
            valor = _num(encontrado.group(1))
            if valor > CERO:
                c.tipo_cambio = valor
                break

    if c.moneda != "ARS" and c.tipo_cambio == CERO:
        c.avisos.append(
            f"La factura esta en {c.moneda} y no se encontro el tipo de cambio. "
            "Cargalo a mano para convertir los impuestos a pesos."
        )


# --- totales -----------------------------------------------------------------

# Cada campo con las formas en que lo escriben los distintos mayoristas.
# El orden importa: lo mas especifico primero, para que "Grav. 10.50 %" no
# quede capturado por el patron de "Grav. 21".
ETIQUETAS: list[tuple[str, tuple[str, ...]]] = [
    ("gravado_105", (
        r"Grav(?:ado)?\.?\s*10[.,]50?\s*%?", r"Neto\s+Gravado\s+10[.,]5",
        r"Base\s+Imponible\s+10[.,]5", r"SERVICIOS\s+GRAVADOS\s+10[.,]5",
    )),
    ("iva_105", (r"I\.?V\.?A\.?\s*\.?\s*10[.,]50?\s*%?",)),
    ("iva_27", (r"I\.?V\.?A\.?\s*\.?\s*27(?:[.,]00?)?\s*%?",)),
    ("iva_21", (r"I\.?V\.?A\.?\s*\.?\s*21(?:[.,]00?)?\s*%?",)),
    ("gravado_21", (
        r"Grav(?:ado)?\.?\s*21(?:[.,]00?)?\s*%?", r"Neto\s+Gravado\s+21",
        r"SERVICIOS\s+GRAVADOS\s+21\s*%?",
    )),
    ("neto_gravado_informado", (
        r"Importe\s+Neto\s+Gravado", r"Neto\s+Gravado", r"Subtotal\s+Gravado",
    )),
    ("no_gravado", (
        r"Importe\s+Neto\s+No\s+Gravado", r"SERVICIOS\s+NO\s+GRAVADOS",
        r"No\s+Gravado", r"No\s+Comp(?:utables?)?\.?",
        r"Srvs\.?\s+no\s+computables[^:]*", r"SERVICIOS\s+NO\s+COMPUTABLES",
        r"Conceptos?\s+No\s+Gravados?", r"Importe\s+Neto\s+No\s+Computable",
    )),
    ("exento", (
        r"Importe\s+Exento", r"Srvs\.?\s+de\s+transporte\s+exento[^:]*",
        r"Operaciones\s+Exentas", r"Exento",
    )),
    ("percepcion_iibb", (
        r"Perc(?:epcion|\.)?\s*I\.?I\.?B\.?B\.?[A-Z]*", 
        r"Perc(?:epcion|\.)?\s*(?:de\s+)?Ingresos\s+Brutos",
    )),
    ("percepcion_iva", (r"Perc(?:epcion|\.)?\s*(?:de\s+)?I\.?V\.?A\.?",)),
    ("otros_tributos", (r"Importe\s+Otros\s+Tributos", r"Otros\s+Tributos")),
    ("total", (
        r"Importe\s+TOTAL", r"TOTAL\s+USD", r"Total\s*\$", r"Importe\s+Total",
        r"Total\s+a\s+pagar", r"\bTOTAL\b",
    )),
]

# Columnas que aparecen en el pie de algunos mayoristas y no se usan, pero hay
# que contarlas: si no, el emparejamiento por orden se desplaza.
COLUMNAS_IGNORADAS = (
    r"Impuesto\s+PAIS", r"Perc\.?\s*RG\s*[/\w]*", r"RG\s*[\d/]+",
    r"Descuento\s*s?/?\s*Neto", r"Subtotal", r"Cantidad", r"U\.?\s*medida",
    r"Precio\s+Unitario", r"Importe\s+Unit",
)

# El encabezado de la tabla de items tambien trae la palabra "Total", pero lo
# que sigue son los renglones del detalle, no el pie de la factura.
ENCABEZADO_DE_DETALLE = re.compile(
    r"(Cant\.?(?:idad)?\b|U\.?\s*medida|Alicuota|Unidad\s+de\s+medida|"
    r"Precio\s+Unit|Importe\s+Unit|Sub\s*Total)", re.I
)
# Un CAE tiene 14 digitos y un numero de reserva puede ser largo: no son importes.
MAX_DIGITOS_IMPORTE = 12


def _es_importe(texto: str) -> bool:
    limpio = texto.strip().strip("$").strip()
    if not re.fullmatch(rf"{IMPORTE}", limpio):
        return False
    return len(re.sub(r"\D", "", limpio)) <= MAX_DIGITOS_IMPORTE


def _totales(c: Comprobante, lineas: list[str], renglones: list[list[Palabra]]) -> None:
    encontrados: dict[str, Decimal] = {}

    _totales_horizontales(encontrados, renglones)

    for atributo, patrones in ETIQUETAS:
        if atributo in encontrados:
            continue
        for patron in patrones:
            valor = _buscar_importe(lineas, patron)
            if valor is not None:
                encontrados[atributo] = valor
                break

    neto_informado = encontrados.pop("neto_gravado_informado", None)
    for campo, valor in encontrados.items():
        setattr(c, campo, valor)

    _repartir_neto(c, neto_informado)
    _completar_faltante(c)


def _repartir_neto(c: Comprobante, neto_informado: Decimal | None) -> None:
    """Separa el neto por alicuota cuando la factura lo informa en un solo total.

    Se deduce desde el IVA de cada alicuota, que es el dato que si viene
    discriminado.
    """
    if neto_informado is None or neto_informado == CERO:
        return
    if c.gravado_21 != CERO or c.gravado_105 != CERO:
        return

    desde_21 = redondear(c.iva_21 / Decimal("0.21")) if c.iva_21 else CERO
    desde_105 = redondear(c.iva_105 / Decimal("0.105")) if c.iva_105 else CERO
    suma = redondear(desde_21 + desde_105)

    if suma != CERO and abs(suma - neto_informado) <= max(
        Decimal("2.00"), abs(neto_informado) * Decimal("0.01")
    ):
        c.gravado_21, c.gravado_105 = desde_21, desde_105
        return

    # Sin forma de separarlo, se imputa a la alicuota que tenga IVA.
    if c.iva_105 != CERO and c.iva_21 == CERO:
        c.gravado_105 = neto_informado
    else:
        c.gravado_21 = neto_informado
        if c.iva_105 != CERO:
            c.avisos.append(
                "La factura informa un solo neto gravado con IVA a dos alicuotas: "
                "no se pudo separar. Revisa el detalle."
            )


def _completar_faltante(c: Comprobante) -> None:
    """Si falta un solo componente, se deduce del total."""
    if c.total == CERO:
        return
    partes = c.total_calculado
    diferencia = redondear(c.total - partes)
    if diferencia == CERO:
        return
    tolerancia = max(Decimal("1.00"), abs(c.total) * Decimal("0.005"))
    if abs(diferencia) <= tolerancia:
        return
    if c.no_gravado == CERO and c.exento == CERO and diferencia > CERO:
        c.no_gravado = diferencia
        c.deducido = True
        c.avisos.append(
            f"Se imputo {diferencia} como no gravado para que la factura cierre "
            "contra el total: no figuraba con esa etiqueta. Verificalo."
        )


def _totales_horizontales(
    encontrados: dict[str, Decimal], renglones: list[list[Palabra]]
) -> None:
    """Lee los pies con las etiquetas en un renglon y los importes en el siguiente.

    Cuando hay tantos importes como etiquetas se emparejan en orden, que es
    mas fiable que medir distancias: los sistemas de facturacion alinean el
    numero a la derecha de su columna y la etiqueta a la izquierda.
    """
    for indice, renglon in enumerate(renglones[:-1]):
        etiquetas = _etiquetas_de_columna(renglon)
        if len(etiquetas) < 3:
            continue
        valores = [
            p for p in sorted(renglones[indice + 1], key=lambda p: p.x)
            if _es_importe(p.texto)
        ]
        if len(valores) < 2:
            continue

        if len(valores) == len(etiquetas):
            pares = list(zip(etiquetas, valores))
        else:
            # Distinta cantidad: cada etiqueta toma el importe mas cercano.
            pares = [
                (etiqueta, min(valores, key=lambda p: abs(p.x - etiqueta[1])))
                for etiqueta in etiquetas
            ]

        for (campo, _), valor in pares:
            if campo is not None:
                encontrados.setdefault(campo, _num(valor.texto))


def _etiquetas_de_columna(renglon: list[Palabra]) -> list[tuple[str | None, float]]:
    """Identifica los encabezados de un pie en columnas, en orden de izquierda a derecha."""
    palabras = sorted(renglon, key=lambda p: p.x)
    texto = _sin_tildes(" ".join(p.texto for p in palabras))

    # Un encabezado puede llevar numeros en la propia etiqueta ("Grav. 21.00 %"),
    # asi que lo que lo descarta es estar compuesto sobre todo por importes,
    # que es como se ve el renglon de valores.
    con_letras = sum(1 for p in palabras if re.search(r"[A-Za-z]{2,}", p.texto))
    importes = sum(1 for p in palabras if _es_importe(p.texto))
    if con_letras < 2 or importes * 2 > len(palabras):
        return []
    if ENCABEZADO_DE_DETALLE.search(texto):
        return []

    encontrados: list[tuple[str | None, float, int]] = []
    usados: set[str] = set()
    ocupado: list[tuple[int, int]] = []

    def registrar(campo, inicio, fin):
        if any(not (fin <= a or inicio >= b) for a, b in ocupado):
            return False
        x = _posicion_de(palabras, inicio, texto)
        if x is None:
            return False
        encontrados.append((campo, x, inicio))
        ocupado.append((inicio, fin))
        return True

    for campo, patrones in ETIQUETAS:
        if campo in usados:
            continue
        for patron in patrones:
            hallado = False
            for encontrado in re.finditer(patron, texto, re.I):
                if registrar(campo, *encontrado.span()):
                    usados.add(campo)
                    hallado = True
                    break
            if hallado:
                break

    # Las columnas que no se usan igual reservan su lugar.
    for patron in COLUMNAS_IGNORADAS:
        for encontrado in re.finditer(patron, texto, re.I):
            registrar(None, *encontrado.span())

    encontrados.sort(key=lambda t: t[2])
    return [(campo, x) for campo, x, _ in encontrados]


def _posicion_de(palabras: list[Palabra], indice: int, texto: str) -> float | None:
    """Traduce una posicion dentro del renglon a la coordenada x de esa palabra."""
    acumulado = 0
    for palabra in palabras:
        largo = len(_sin_tildes(palabra.texto))
        if acumulado <= indice <= acumulado + largo:
            return palabra.x
        acumulado += largo + 1
    return palabras[0].x if palabras else None


def _buscar_importe(lineas: list[str], patron: str) -> Decimal | None:
    """Toma el importe que sigue a una etiqueta dentro del mismo renglon.

    Los pies suelen traer varios pares por renglon ("Gravado 21%: 84.11
    Iva 21%: 17.66"), asi que se corta al llegar a la siguiente palabra.
    """
    expresion = re.compile(patron, re.I)
    for indice, linea in enumerate(lineas):
        encontrado = expresion.search(linea)
        if not encontrado:
            continue
        resto = re.sub(r"^\s*[:\-]?\s*(?:AR)?\$?\s*", "", linea[encontrado.end() :])
        corte = re.search(r"[A-Za-z]{3,}", resto)
        candidatos = [
            x for x in re.findall(IMPORTE, resto[: corte.start()] if corte else resto)
            if _es_importe(x)
        ]
        if candidatos:
            # Tres o mas importes seguidos son cantidad, unitario y subtotal:
            # el que corresponde es el ultimo.
            return _num(candidatos[-1] if len(candidatos) >= 3 else candidatos[0])
        if indice + 1 < len(lineas) and not re.search(r"[A-Za-z]{4,}", lineas[indice + 1]):
            for candidato in re.findall(IMPORTE, lineas[indice + 1]):
                if _es_importe(candidato):
                    return _num(candidato)
    return None


INICIO_DETALLE = re.compile(
    r"(Detalle|Descripcion|Producto\s*/?\s*Servicio|Servicios|Concepto)", re.I
)
FIN_DETALLE = re.compile(
    r"(Importe\s+Neto|Importe\s+TOTAL|TOTAL\s+USD|Subtotal\s+Import|Otros\s+tributos|"
    r"Grav(?:ado)?\.?\s*21|Exento\s+No\s+|CAE|Regimen\s+de\s+Transparencia|"
    r"FACTURA\s+EMITIDA)", re.I
)


def _conceptos(c: Comprobante, lineas: list[str]) -> None:
    inicio = None
    for indice, linea in enumerate(lineas):
        if INICIO_DETALLE.search(linea) and not re.search(IMPORTE + r"\s*$", linea.strip()):
            inicio = indice + 1
            break
    if inicio is None:
        return

    for linea in lineas[inicio:]:
        if FIN_DETALLE.search(linea):
            break
        importes = [x for x in re.findall(IMPORTE, linea) if _es_importe(x)]
        if not importes:
            continue
        importe = _num(importes[-1])
        if importe == CERO:
            continue
        # La descripcion es todo lo anterior al ultimo importe del renglon.
        descripcion = linea[: linea.rfind(importes[-1])].strip()
        # Un codigo al principio se separa de la descripcion.
        codigo = ""
        partes = descripcion.split(None, 1)
        if len(partes) == 2 and re.fullmatch(r"[A-Z0-9][A-Z0-9\-./]{1,14}", partes[0], re.I):
            codigo, descripcion = partes[0], partes[1]
        descripcion = re.sub(rf"(?:\s|{IMPORTE})+$", "", descripcion).strip()
        if len(descripcion) < 3:
            continue
        alicuota = None
        marca = re.search(r"\b(21|10[.,]5|27)\s*%", linea)
        if marca:
            alicuota = _num(marca.group(1))
        c.conceptos.append(
            ConceptoFactura(
                codigo=codigo,
                descripcion=descripcion[:120],
                importe=importe,
                alicuota_iva=alicuota,
            )
        )


def _referencias(c: Comprobante, texto: str) -> None:
    file = re.search(r"\b(?:File|Legajo|Negocio|Expediente)\s*:?\s*([A-Z0-9\-]{3,15})", texto, re.I)
    if file:
        c.referencia = file.group(1)

    pax = re.search(
        r"(?:Grupo\s+de\s+Pax|Pasajeros?|Pax)\s*:?\s*([A-ZÑ][A-ZÑ\s,/\.]{3,60})", texto, re.I
    )
    if pax:
        c.pasajeros = re.sub(r"\s+", " ", pax.group(1)).strip()
    elif c.referencia:
        contexto = re.search(
            rf"{re.escape(c.referencia)}\s*[-–]?\s*([A-ZÑ][A-ZÑ\s,/\.]{{5,60}})", texto
        )
        if contexto:
            c.pasajeros = re.sub(r"\s+", " ", contexto.group(1)).strip()


def _controlar(c: Comprobante) -> None:
    """Cruza los importes contra el total: es el unico control real de la lectura."""
    if c.total != CERO:
        diferencia = abs(c.total_calculado - c.total)
        tolerancia = max(Decimal("1.00"), abs(c.total) * Decimal("0.005"))
        if diferencia > tolerancia:
            c.confiable = False
            c.avisos.append(
                f"Los importes no cierran: las partes suman {c.total_calculado} y el "
                f"total dice {c.total} (diferencia {redondear(diferencia)}). "
                "Revisa la factura antes de usarla."
            )

    if c.letra in ("B", "C") and c.iva_total == CERO and c.total != CERO:
        c.avisos.append(
            f"Factura {c.letra}: el IVA no viene discriminado, no genera credito fiscal."
        )
    if not c.cae:
        c.avisos.append("No se encontro el CAE en el comprobante.")
    if c.deducido:
        c.confiable = False
    if c.motor_pdf == "ocr":
        c.confiable = False

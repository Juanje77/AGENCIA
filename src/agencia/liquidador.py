"""Liquidacion de IVA e Ingresos Brutos del periodo.

Sigue el criterio con el que trabaja la agencia:

  * el mayorista factura el viaje y le reconoce un porcentaje de comision
    sobre la parte comisionable (el servicio en si); las tasas y cargos que
    van como no gravados no pagan comision;
  * esa comision viene con el IVA adentro, asi que para determinar el debito
    fiscal hay que desagregarla: gravado = comision / 1,21;
  * el servicio propio es el recargo que la agencia le factura al pasajero:
    es neto y genera su propio debito;
  * la base de Ingresos Brutos es la comision neta mas el servicio propio.

Cuando la factura del mayorista es A, el IVA discriminado que le cobro a la
agencia es credito fiscal y se resta del debito del periodo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import dir_config
from .dinero import CERO, CIEN, dec, pct, redondear
from .liquidaciones.factura import COMPRA, Comprobante

ALICUOTA_DEFAULT = Decimal("21")


@dataclass
class Mayorista:
    nombre: str
    comision_pct: Decimal = CERO
    iva_pct: Decimal = ALICUOTA_DEFAULT
    cuit: str = ""
    alias: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Se normalizan a dos decimales: si no, el mismo porcentaje se guarda
        # como "5" o "5.00" segun como lo haya tipeado el operador.
        self.comision_pct = redondear(dec(self.comision_pct))
        self.iva_pct = redondear(dec(self.iva_pct))

    @property
    def cuit_normalizado(self) -> str:
        return "".join(c for c in self.cuit if c.isdigit())

    def coincide(self, nombre: str = "", cuit: str = "") -> bool:
        digitos = "".join(c for c in cuit if c.isdigit())
        if digitos and self.cuit_normalizado and digitos == self.cuit_normalizado:
            return True
        if not nombre:
            return False
        buscado = nombre.upper()
        if self.nombre.upper() in buscado:
            return True
        return any(a.upper() in buscado for a in self.alias)

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "comision_pct": str(self.comision_pct),
            "iva_pct": str(self.iva_pct),
            "cuit": self.cuit,
            "alias": self.alias,
        }


@dataclass
class DatosAgencia:
    razon_social: str = ""
    cuit: str = ""
    condicion_iva: str = "RESPONSABLE_INSCRIPTO"
    jurisdiccion: str = "LA_PAMPA"
    alicuota_iibb: Decimal = Decimal("3.50")

    def __post_init__(self) -> None:
        self.alicuota_iibb = redondear(dec(self.alicuota_iibb))


@dataclass
class Padron:
    """Los mayoristas con los que trabaja la agencia."""

    agencia: DatosAgencia = field(default_factory=DatosAgencia)
    mayoristas: list[Mayorista] = field(default_factory=list)

    def buscar(self, nombre: str = "", cuit: str = "") -> Mayorista | None:
        for mayorista in self.mayoristas:
            if mayorista.coincide(nombre, cuit):
                return mayorista
        return None

    def a_dict(self) -> dict:
        return {
            "agencia": {
                "razon_social": self.agencia.razon_social,
                "cuit": self.agencia.cuit,
                "condicion_iva": self.agencia.condicion_iva,
                "jurisdiccion": self.agencia.jurisdiccion,
                "alicuota_iibb": str(self.agencia.alicuota_iibb),
            },
            "mayoristas": [m.a_dict() for m in self.mayoristas],
        }


def cargar_padron(ruta: str | Path | None = None) -> Padron:
    archivo = Path(ruta) if ruta else dir_config() / "mayoristas.json"
    if not archivo.exists():
        return Padron()
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    return Padron(
        agencia=DatosAgencia(**{
            k: v for k, v in (datos.get("agencia") or {}).items()
            if k in DatosAgencia.__dataclass_fields__
        }),
        mayoristas=[
            Mayorista(**{k: v for k, v in m.items() if k in Mayorista.__dataclass_fields__})
            for m in datos.get("mayoristas", [])
        ],
    )


def guardar_padron(padron: Padron, ruta: str | Path | None = None) -> Path:
    archivo = Path(ruta) if ruta else dir_config() / "mayoristas.json"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(
        json.dumps(padron.a_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return archivo


@dataclass
class Operacion:
    """Una venta del periodo, con lo que factura el mayorista y lo que gana la agencia."""

    fecha: str = ""
    cliente: str = ""
    mayorista: str = ""
    referencia: str = ""
    comisionable: Decimal = CERO
    no_comisionable: Decimal = CERO
    comision_pct: Decimal = CERO
    iva_pct: Decimal = ALICUOTA_DEFAULT
    servicio_propio_pct: Decimal = CERO
    moneda: str = "ARS"
    tipo_cambio: Decimal = CERO
    credito_fiscal: Decimal = CERO
    """IVA discriminado en la factura de compra del mayorista."""
    comprobante: str = ""
    origen: str = "manual"
    avisos: list[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        for campo in (
            "comisionable", "no_comisionable", "comision_pct", "iva_pct",
            "servicio_propio_pct", "tipo_cambio", "credito_fiscal",
        ):
            setattr(self, campo, dec(getattr(self, campo)))

    # --- conversion a pesos ----------------------------------------------

    @property
    def factor(self) -> Decimal:
        if self.moneda == "ARS":
            return Decimal("1")
        return self.tipo_cambio if self.tipo_cambio > CERO else CERO

    @property
    def convertible(self) -> bool:
        return self.factor > CERO

    def _pesos(self, valor: Decimal) -> Decimal:
        return redondear(valor * self.factor)

    # --- calculo ----------------------------------------------------------

    @property
    def total_viaje(self) -> Decimal:
        return redondear(self.comisionable + self.no_comisionable)

    @property
    def comision_ganada(self) -> Decimal:
        """Comision bruta: viene con el IVA adentro."""
        return pct(self.comisionable, self.comision_pct)

    @property
    def gravado(self) -> Decimal:
        """Comision neta, una vez desagregado el IVA."""
        divisor = 1 + self.iva_pct / CIEN
        return redondear(self.comision_ganada / divisor) if divisor else self.comision_ganada

    @property
    def iva_comision(self) -> Decimal:
        return redondear(self.comision_ganada - self.gravado)

    @property
    def servicio_propio(self) -> Decimal:
        """Recargo propio de la agencia, neto de IVA."""
        return pct(self.total_viaje, self.servicio_propio_pct)

    @property
    def iva_servicio(self) -> Decimal:
        return pct(self.servicio_propio, self.iva_pct)

    @property
    def debito_fiscal(self) -> Decimal:
        return redondear(self.iva_comision + self.iva_servicio)

    @property
    def base_iibb(self) -> Decimal:
        return redondear(self.gravado + self.servicio_propio)

    def a_dict(self) -> dict:
        return {
            "id": self.id,
            "fecha": self.fecha,
            "cliente": self.cliente,
            "mayorista": self.mayorista,
            "referencia": self.referencia,
            "comprobante": self.comprobante,
            "origen": self.origen,
            "moneda": self.moneda,
            "tipo_cambio": str(self.tipo_cambio),
            "comisionable": str(self.comisionable),
            "no_comisionable": str(self.no_comisionable),
            "total_viaje": str(self.total_viaje),
            "comision_pct": str(self.comision_pct),
            "iva_pct": str(self.iva_pct),
            "comision_ganada": str(self.comision_ganada),
            "gravado": str(self.gravado),
            "iva_comision": str(self.iva_comision),
            "servicio_propio_pct": str(self.servicio_propio_pct),
            "servicio_propio": str(self.servicio_propio),
            "iva_servicio": str(self.iva_servicio),
            "debito_fiscal": str(self.debito_fiscal),
            "base_iibb": str(self.base_iibb),
            "credito_fiscal": str(self.credito_fiscal),
            "convertible": self.convertible,
            "avisos": self.avisos,
            # En pesos, que es como se declara.
            "pesos": {
                "comisionable": str(self._pesos(self.comisionable)),
                "no_comisionable": str(self._pesos(self.no_comisionable)),
                "comision_ganada": str(self._pesos(self.comision_ganada)),
                "gravado": str(self._pesos(self.gravado)),
                "iva_comision": str(self._pesos(self.iva_comision)),
                "servicio_propio": str(self._pesos(self.servicio_propio)),
                "iva_servicio": str(self._pesos(self.iva_servicio)),
                "debito_fiscal": str(self._pesos(self.debito_fiscal)),
                "base_iibb": str(self._pesos(self.base_iibb)),
                "credito_fiscal": str(self._pesos(self.credito_fiscal)),
            } if self.convertible else None,
        }


@dataclass
class Periodo:
    """La liquidacion de un mes."""

    periodo: str = ""
    operaciones: list[Operacion] = field(default_factory=list)
    credito_fiscal_extra: Decimal = CERO
    """IVA de compras y gastos propios que no salen de las facturas cargadas."""
    computa_credito_de_mayoristas: bool = False
    """Si el IVA de las facturas de los mayoristas se toma como credito fiscal.

    Depende de como factura la agencia. Actuando como intermediaria por cuenta
    y orden de terceros, factura solo su comision y ese IVA no es suyo: el
    destinatario del servicio es el pasajero. Si en cambio revende por cuenta
    propia y le factura al pasajero el viaje completo, si lo computa. Por eso
    viene desactivado: lo tiene que definir el contador de la agencia.
    """
    alicuota_iibb: Decimal = Decimal("3.50")
    jurisdiccion: str = "La Pampa"
    retenciones_iibb_sufridas: Decimal = CERO

    def __post_init__(self) -> None:
        for campo in ("credito_fiscal_extra", "alicuota_iibb", "retenciones_iibb_sufridas"):
            setattr(self, campo, dec(getattr(self, campo)))

    # --- totales, siempre en pesos ---------------------------------------

    def _sumar(self, atributo: str) -> Decimal:
        total = CERO
        for operacion in self.operaciones:
            if not operacion.convertible:
                continue
            total += getattr(operacion, atributo) * operacion.factor
        return redondear(total)

    @property
    def operaciones_sin_convertir(self) -> list[Operacion]:
        return [o for o in self.operaciones if not o.convertible]

    @property
    def debito_fiscal(self) -> Decimal:
        return self._sumar("debito_fiscal")

    @property
    def credito_fiscal_mayoristas(self) -> Decimal:
        return self._sumar("credito_fiscal")

    @property
    def credito_fiscal(self) -> Decimal:
        credito = self.credito_fiscal_extra
        if self.computa_credito_de_mayoristas:
            credito += self.credito_fiscal_mayoristas
        return redondear(credito)

    @property
    def iva_resultado(self) -> Decimal:
        """Positivo: a pagar. Negativo: saldo tecnico a favor."""
        return redondear(self.debito_fiscal - self.credito_fiscal)

    @property
    def base_iibb(self) -> Decimal:
        return self._sumar("base_iibb")

    @property
    def iibb_determinado(self) -> Decimal:
        return pct(self.base_iibb, self.alicuota_iibb)

    @property
    def iibb_a_pagar(self) -> Decimal:
        return redondear(self.iibb_determinado - self.retenciones_iibb_sufridas)

    @property
    def comision_ganada(self) -> Decimal:
        return self._sumar("comision_ganada")

    @property
    def carga_total(self) -> Decimal:
        return redondear(max(self.iva_resultado, CERO) + self.iibb_determinado)

    @property
    def ganancia_neta(self) -> Decimal:
        bruto = redondear(self._sumar("gravado") + self._sumar("servicio_propio"))
        return redondear(bruto - self.iibb_determinado)

    def avisos(self) -> list[str]:
        avisos: list[str] = []
        sin_convertir = self.operaciones_sin_convertir
        if sin_convertir:
            avisos.append(
                f"{len(sin_convertir)} operacion(es) en moneda extranjera sin tipo de "
                "cambio: no entran en los totales. Cargales la cotizacion."
            )
        sin_comision = [
            o for o in self.operaciones if o.comision_pct == CERO and o.comisionable > CERO
        ]
        if sin_comision:
            avisos.append(
                f"{len(sin_comision)} operacion(es) sin porcentaje de comision. "
                "Revisa el mayorista en la pantalla de configuracion."
            )
        if self.iva_resultado < CERO:
            avisos.append(
                "El credito fiscal supera al debito: queda saldo tecnico a favor "
                "para trasladar al periodo siguiente."
            )
        if not self.computa_credito_de_mayoristas and self.credito_fiscal_mayoristas > CERO:
            avisos.append(
                f"Las facturas de los mayoristas traen {self.credito_fiscal_mayoristas} "
                "de IVA discriminado que no se esta computando como credito fiscal. "
                "Corresponde computarlo solo si la agencia le factura al pasajero el "
                "viaje completo por cuenta propia, no si actua como intermediaria. "
                "Definilo con tu contador."
            )
        return avisos

    def a_dict(self) -> dict:
        return {
            "periodo": self.periodo,
            "jurisdiccion": self.jurisdiccion,
            "alicuota_iibb": str(self.alicuota_iibb),
            "operaciones": [o.a_dict() for o in self.operaciones],
            "totales": {
                "operaciones": len(self.operaciones),
                "comisionable": str(self._sumar("comisionable")),
                "no_comisionable": str(self._sumar("no_comisionable")),
                "total_viaje": str(self._sumar("total_viaje")),
                "comision_ganada": str(self.comision_ganada),
                "gravado": str(self._sumar("gravado")),
                "iva_comision": str(self._sumar("iva_comision")),
                "servicio_propio": str(self._sumar("servicio_propio")),
                "iva_servicio": str(self._sumar("iva_servicio")),
            },
            "iva": {
                "debito_fiscal": str(self.debito_fiscal),
                "credito_fiscal": str(self.credito_fiscal),
                "credito_fiscal_extra": str(self.credito_fiscal_extra),
                "credito_fiscal_mayoristas": str(self.credito_fiscal_mayoristas),
                "computa_credito_de_mayoristas": self.computa_credito_de_mayoristas,
                "resultado": str(self.iva_resultado),
                "a_pagar": str(max(self.iva_resultado, CERO)),
                "saldo_a_favor": str(max(-self.iva_resultado, CERO)),
            },
            "iibb": {
                "base": str(self.base_iibb),
                "alicuota": str(self.alicuota_iibb),
                "determinado": str(self.iibb_determinado),
                "retenciones_sufridas": str(self.retenciones_iibb_sufridas),
                "a_pagar": str(self.iibb_a_pagar),
            },
            "resumen": {
                "carga_total": str(self.carga_total),
                "ganancia_neta": str(self.ganancia_neta),
            },
            "avisos": self.avisos(),
        }


def operacion_desde_comprobante(
    comprobante: Comprobante,
    padron: Padron | None = None,
    servicio_propio_pct: Any = CERO,
) -> Operacion:
    """Arma la fila del liquidador a partir de una factura ya leida.

    Lo comisionable es el servicio (gravado mas exento) y lo no comisionable
    son las tasas y cargos que el mayorista factura como no gravados.
    """
    padron = padron or Padron()
    mayorista = padron.buscar(
        comprobante.razon_social_emisor, comprobante.cuit_emisor
    )

    operacion = Operacion(
        fecha=comprobante.fecha_emision,
        cliente=comprobante.pasajeros or comprobante.razon_social_receptor,
        mayorista=mayorista.nombre if mayorista else comprobante.razon_social_emisor,
        referencia=comprobante.referencia,
        comprobante=comprobante.identificacion,
        comisionable=comprobante.comisionable,
        no_comisionable=comprobante.no_comisionable,
        comision_pct=mayorista.comision_pct if mayorista else CERO,
        iva_pct=mayorista.iva_pct if mayorista else ALICUOTA_DEFAULT,
        servicio_propio_pct=dec(servicio_propio_pct),
        moneda=comprobante.moneda,
        tipo_cambio=comprobante.tipo_cambio,
        credito_fiscal=comprobante.credito_fiscal,
        origen=f"factura:{comprobante.archivo}",
        avisos=list(comprobante.avisos),
    )

    if mayorista is None:
        operacion.avisos.append(
            f"El mayorista '{comprobante.razon_social_emisor}' no esta en la "
            "configuracion: carga su porcentaje de comision para que la operacion "
            "sume al calculo."
        )
    if comprobante.sentido != COMPRA:
        operacion.avisos.append(
            "El comprobante figura emitido por la agencia, no recibido: revisa el "
            "sentido antes de liquidarlo."
        )
    if not comprobante.confiable:
        operacion.avisos.append(
            "La lectura del PDF no cerro contra el total: verifica los importes."
        )
    return operacion

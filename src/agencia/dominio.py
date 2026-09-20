"""Vocabulario comun del sistema: monedas, roles, tipos de servicio."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from .dinero import CERO, dec


class Moneda(str, Enum):
    ARS = "ARS"
    USD = "USD"
    EUR = "EUR"
    BRL = "BRL"


class RolAgencia(str, Enum):
    """Como participa la agencia en la operacion.

    Define la base imponible: el intermediario tributa sobre su comision,
    el organizador sobre el total que factura.
    """

    INTERMEDIARIO = "INTERMEDIARIO"
    ORGANIZADOR = "ORGANIZADOR"


class TratamientoIVA(str, Enum):
    GRAVADO_21 = "GRAVADO_21"
    GRAVADO_105 = "GRAVADO_105"
    EXENTO = "EXENTO"
    NO_GRAVADO = "NO_GRAVADO"
    EXPORTACION = "EXPORTACION"


class BaseIIBB(str, Enum):
    COMISION = "COMISION"
    DIFERENCIA = "DIFERENCIA"
    TOTAL = "TOTAL"


class CondicionIVA(str, Enum):
    RESPONSABLE_INSCRIPTO = "RESPONSABLE_INSCRIPTO"
    MONOTRIBUTO = "MONOTRIBUTO"
    EXENTO = "EXENTO"
    CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"


@dataclass(frozen=True)
class TipoCambio:
    """Cotizacion usada para pasar un importe a la moneda base."""

    moneda: Moneda
    valor: Decimal
    fecha: str = ""

    def a_pesos(self, importe: Decimal) -> Decimal:
        if self.moneda == Moneda.ARS:
            return dec(importe)
        return dec(importe) * dec(self.valor)


@dataclass
class Cotizador:
    """Conjunto de tipos de cambio vigentes para una operacion."""

    tipos: dict[Moneda, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tipos = {Moneda(k): dec(v) for k, v in self.tipos.items()}
        self.tipos.setdefault(Moneda.ARS, Decimal("1"))

    def a_pesos(self, importe: Decimal, moneda: Moneda | str) -> Decimal:
        moneda = Moneda(moneda)
        if moneda == Moneda.ARS:
            return dec(importe)
        if moneda not in self.tipos:
            raise ValueError(
                f"Falta el tipo de cambio de {moneda.value}. "
                "Cargalo antes de calcular impuestos."
            )
        return dec(importe) * self.tipos[moneda]

    def valor(self, moneda: Moneda | str) -> Decimal:
        return self.tipos.get(Moneda(moneda), CERO)

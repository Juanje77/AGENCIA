"""Estructuras de entrada y salida del motor fiscal.

Tanto el presupuestador como el lector de liquidaciones traducen sus datos a
una `OperacionGravada`, de modo que el calculo de impuestos sea uno solo y el
presupuesto y la liquidacion sean comparables entre si.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..dinero import CERO, dec, redondear
from ..dominio import BaseIIBB, Moneda, RolAgencia, TratamientoIVA


@dataclass
class OperacionGravada:
    """Una linea de venta lista para calcular impuestos. Importes en pesos."""

    tipo_servicio: str
    rol: RolAgencia = RolAgencia.INTERMEDIARIO
    costo_neto: Decimal = CERO
    """Lo que la agencia le paga al proveedor, sin IVA."""
    iva_credito_proveedor: Decimal = CERO
    """IVA discriminado en la factura del proveedor (solo computable como organizador)."""
    comision: Decimal = CERO
    """Comision que reconoce el proveedor o mayorista, sin IVA."""
    over: Decimal = CERO
    """Sobreprecio que la agencia le agrega al pasajero por sobre la tarifa."""
    fee: Decimal = CERO
    """Cargo de gestion propio de la agencia (siempre gravado al 21%)."""
    jurisdiccion: str | None = None
    base_iibb_forzada: BaseIIBB | None = None
    cantidad: int = 1
    descripcion: str = ""
    referencia: str = ""
    moneda_origen: Moneda = Moneda.ARS
    importe_origen: Decimal = CERO

    def __post_init__(self) -> None:
        for campo in ("costo_neto", "iva_credito_proveedor", "comision", "over", "fee", "importe_origen"):
            setattr(self, campo, dec(getattr(self, campo)))
        if isinstance(self.rol, str):
            self.rol = RolAgencia(self.rol)

    @property
    def retribucion_agencia(self) -> Decimal:
        """Todo lo que gana la agencia por la operacion, sin IVA."""
        return redondear(self.comision + self.over + self.fee)

    @property
    def precio_venta_neto(self) -> Decimal:
        """Precio al pasajero sin IVA (el costo mas lo que agrega la agencia)."""
        return redondear(self.costo_neto + self.over + self.fee)


@dataclass
class DesgloseIVA:
    tratamiento: TratamientoIVA
    concepto: str
    base: Decimal
    alicuota: Decimal
    impuesto: Decimal

    def a_dict(self) -> dict:
        return {
            "tratamiento": self.tratamiento.value,
            "concepto": self.concepto,
            "base": str(self.base),
            "alicuota": str(self.alicuota),
            "impuesto": str(self.impuesto),
        }


@dataclass
class DistribucionIIBB:
    jurisdiccion: str
    etiqueta: str
    base: Decimal
    coeficiente: Decimal
    alicuota: Decimal
    impuesto: Decimal

    def a_dict(self) -> dict:
        return {
            "jurisdiccion": self.jurisdiccion,
            "etiqueta": self.etiqueta,
            "base": str(self.base),
            "coeficiente": str(self.coeficiente),
            "alicuota": str(self.alicuota),
            "impuesto": str(self.impuesto),
        }


@dataclass
class RetencionCalculada:
    codigo: str
    etiqueta: str
    base: Decimal
    alicuota: Decimal
    importe: Decimal
    aplicada: bool = True
    motivo: str = ""

    def a_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "etiqueta": self.etiqueta,
            "base": str(self.base),
            "alicuota": str(self.alicuota),
            "importe": str(self.importe),
            "aplicada": self.aplicada,
            "motivo": self.motivo,
        }


@dataclass
class ResultadoFiscal:
    """Lo que la operacion genera de impuestos."""

    operacion: OperacionGravada
    desglose_iva: list[DesgloseIVA] = field(default_factory=list)
    debito_fiscal: Decimal = CERO
    credito_fiscal: Decimal = CERO
    base_iibb: Decimal = CERO
    base_iibb_tipo: BaseIIBB = BaseIIBB.COMISION
    iibb_total: Decimal = CERO
    distribucion_iibb: list[DistribucionIIBB] = field(default_factory=list)
    retenciones: list[RetencionCalculada] = field(default_factory=list)
    observaciones: list[str] = field(default_factory=list)

    @property
    def iva_a_pagar(self) -> Decimal:
        return redondear(self.debito_fiscal - self.credito_fiscal)

    @property
    def retenciones_totales(self) -> Decimal:
        return redondear(sum((r.importe for r in self.retenciones if r.aplicada), CERO))

    @property
    def retribucion_bruta(self) -> Decimal:
        return self.operacion.retribucion_agencia

    @property
    def carga_impositiva(self) -> Decimal:
        """IVA a pagar mas Ingresos Brutos. Las retenciones no suman: son pagos a cuenta."""
        return redondear(self.iva_a_pagar + self.iibb_total)

    @property
    def margen_neto(self) -> Decimal:
        """Lo que le queda a la agencia despues de IVA e IIBB."""
        return redondear(self.retribucion_bruta - self.carga_impositiva)

    @property
    def margen_neto_pct(self) -> Decimal:
        if self.retribucion_bruta == CERO:
            return CERO
        return redondear(self.margen_neto / self.retribucion_bruta * 100)

    def a_dict(self) -> dict:
        return {
            "descripcion": self.operacion.descripcion,
            "tipo_servicio": self.operacion.tipo_servicio,
            "rol": self.operacion.rol.value,
            "retribucion_bruta": str(self.retribucion_bruta),
            "desglose_iva": [d.a_dict() for d in self.desglose_iva],
            "debito_fiscal": str(self.debito_fiscal),
            "credito_fiscal": str(self.credito_fiscal),
            "iva_a_pagar": str(self.iva_a_pagar),
            "base_iibb": str(self.base_iibb),
            "base_iibb_tipo": self.base_iibb_tipo.value,
            "iibb_total": str(self.iibb_total),
            "distribucion_iibb": [d.a_dict() for d in self.distribucion_iibb],
            "retenciones": [r.a_dict() for r in self.retenciones],
            "retenciones_totales": str(self.retenciones_totales),
            "carga_impositiva": str(self.carga_impositiva),
            "margen_neto": str(self.margen_neto),
            "margen_neto_pct": str(self.margen_neto_pct),
            "observaciones": self.observaciones,
        }

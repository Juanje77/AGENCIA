"""Modelo de una liquidacion de mayorista ya normalizada."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..dinero import CERO, dec, redondear
from ..dominio import Moneda, RolAgencia

CAMPOS_IMPORTE = (
    "importe_total",
    "costo_neto",
    "comision",
    "iva_comision",
    "over",
    "ret_ganancias",
    "ret_iva",
    "ret_iibb",
    "otros_descuentos",
    "neto_a_cobrar",
    "tipo_cambio",
)


@dataclass
class LineaLiquidacion:
    """Una reserva dentro de la liquidacion del mayorista.

    Los campos `ret_*` son lo que el mayorista dice haber retenido. El sistema
    los conserva tal cual para poder compararlos con lo que correspondia.
    """

    referencia: str = ""
    fecha: str = ""
    pasajero: str = ""
    destino: str = ""
    proveedor: str = ""
    servicio_descripcion: str = ""
    tipo_servicio: str = "OTRO"
    moneda: Moneda = Moneda.ARS
    tipo_cambio: Decimal = CERO
    importe_total: Decimal = CERO
    costo_neto: Decimal = CERO
    comision: Decimal = CERO
    iva_comision: Decimal = CERO
    over: Decimal = CERO
    ret_ganancias: Decimal = CERO
    ret_iva: Decimal = CERO
    ret_iibb: Decimal = CERO
    otros_descuentos: Decimal = CERO
    neto_a_cobrar: Decimal = CERO
    rol: RolAgencia = RolAgencia.INTERMEDIARIO
    jurisdiccion: str | None = None
    fila: int = 0
    crudo: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for campo in CAMPOS_IMPORTE:
            setattr(self, campo, dec(getattr(self, campo)))
        if isinstance(self.moneda, str):
            self.moneda = Moneda(self.moneda)
        if isinstance(self.rol, str):
            self.rol = RolAgencia(self.rol)

    @property
    def retenciones_informadas(self) -> Decimal:
        return redondear(self.ret_ganancias + self.ret_iva + self.ret_iibb)

    @property
    def comision_con_iva(self) -> Decimal:
        return redondear(self.comision + self.iva_comision)

    def comision_en_pesos(self, cotizacion: Decimal | None = None) -> Decimal:
        """Convierte la comision a pesos usando el TC de la linea o el provisto."""
        if self.moneda is Moneda.ARS:
            return self.comision
        tc = dec(cotizacion) if cotizacion else self.tipo_cambio
        if tc <= CERO:
            raise ValueError(
                f"Linea {self.referencia or self.fila}: falta el tipo de cambio "
                f"para convertir {self.moneda.value} a pesos."
            )
        return redondear(self.comision * tc)

    def a_dict(self) -> dict:
        datos = {
            "referencia": self.referencia,
            "fecha": self.fecha,
            "pasajero": self.pasajero,
            "destino": self.destino,
            "proveedor": self.proveedor,
            "servicio_descripcion": self.servicio_descripcion,
            "tipo_servicio": self.tipo_servicio,
            "moneda": self.moneda.value,
            "rol": self.rol.value,
            "fila": self.fila,
            "avisos": self.avisos,
        }
        datos.update({campo: str(getattr(self, campo)) for campo in CAMPOS_IMPORTE})
        return datos


@dataclass
class Liquidacion:
    """El archivo completo que mando el mayorista."""

    mayorista: str = ""
    numero: str = ""
    periodo: str = ""
    fecha: str = ""
    archivo_origen: str = ""
    perfil_usado: str = "auto"
    moneda: Moneda = Moneda.ARS
    tipo_cambio: Decimal = CERO
    lineas: list[LineaLiquidacion] = field(default_factory=list)
    columnas_detectadas: dict[str, str] = field(default_factory=dict)
    columnas_ignoradas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    comprobante: object | None = None
    """La factura de origen, cuando la liquidacion vino de un PDF."""

    def __post_init__(self) -> None:
        self.tipo_cambio = dec(self.tipo_cambio)
        if isinstance(self.moneda, str):
            self.moneda = Moneda(self.moneda)

    @property
    def cantidad_lineas(self) -> int:
        return len(self.lineas)

    def total(self, campo: str) -> Decimal:
        return redondear(sum((getattr(l, campo) for l in self.lineas), CERO))

    def resumen(self) -> dict:
        return {
            "mayorista": self.mayorista,
            "numero": self.numero,
            "periodo": self.periodo,
            "archivo_origen": self.archivo_origen,
            "perfil_usado": self.perfil_usado,
            "lineas": self.cantidad_lineas,
            "importe_total": str(self.total("importe_total")),
            "costo_neto": str(self.total("costo_neto")),
            "comision": str(self.total("comision")),
            "iva_comision": str(self.total("iva_comision")),
            "ret_ganancias": str(self.total("ret_ganancias")),
            "ret_iva": str(self.total("ret_iva")),
            "ret_iibb": str(self.total("ret_iibb")),
            "neto_a_cobrar": str(self.total("neto_a_cobrar")),
            "comprobante": self.comprobante.a_dict() if self.comprobante else None,
            "columnas_detectadas": self.columnas_detectadas,
            "columnas_ignoradas": self.columnas_ignoradas,
            "avisos": self.avisos,
        }

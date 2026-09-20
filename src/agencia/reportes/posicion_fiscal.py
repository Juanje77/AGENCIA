"""Posicion de IVA e Ingresos Brutos de un periodo.

Junta todas las liquidaciones conciliadas del mes y arma los numeros que van
a la declaracion jurada: debito fiscal por alicuota, base y saldo de Ingresos
Brutos por jurisdiccion, y retenciones sufridas para computar como pago a
cuenta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..config import ParametrosFiscales, cargar_parametros
from ..dinero import CERO, dec, redondear
from ..liquidaciones.conciliacion import Conciliacion


@dataclass
class PosicionFiscal:
    periodo: str = ""
    liquidaciones: list[str] = field(default_factory=list)
    operaciones: int = 0

    # IVA
    debito_fiscal: Decimal = CERO
    credito_fiscal: Decimal = CERO
    retenciones_iva_sufridas: Decimal = CERO
    por_tratamiento: dict[str, dict[str, Decimal]] = field(default_factory=dict)

    # Ingresos Brutos
    iibb_por_jurisdiccion: dict[str, dict] = field(default_factory=dict)
    retenciones_iibb_sufridas: Decimal = CERO

    # Ganancias
    retenciones_ganancias_sufridas: Decimal = CERO

    retribucion_bruta: Decimal = CERO
    diferencias_detectadas: int = 0
    diferencias_altas: int = 0
    importe_en_disputa: Decimal = CERO
    avisos: list[str] = field(default_factory=list)

    @property
    def iva_determinado(self) -> Decimal:
        return redondear(self.debito_fiscal - self.credito_fiscal)

    @property
    def iva_a_ingresar(self) -> Decimal:
        """Saldo a pagar despues de computar las retenciones sufridas."""
        return redondear(self.iva_determinado - self.retenciones_iva_sufridas)

    @property
    def iibb_determinado(self) -> Decimal:
        return redondear(
            sum((dec(v["impuesto"]) for v in self.iibb_por_jurisdiccion.values()), CERO)
        )

    @property
    def iibb_a_ingresar(self) -> Decimal:
        return redondear(self.iibb_determinado - self.retenciones_iibb_sufridas)

    @property
    def carga_total(self) -> Decimal:
        return redondear(self.iva_determinado + self.iibb_determinado)

    @property
    def margen_neto(self) -> Decimal:
        return redondear(self.retribucion_bruta - self.carga_total)

    @property
    def presion_fiscal_pct(self) -> Decimal:
        if self.retribucion_bruta == CERO:
            return CERO
        return redondear(self.carga_total / self.retribucion_bruta * 100)

    def a_dict(self) -> dict:
        return {
            "periodo": self.periodo,
            "liquidaciones": self.liquidaciones,
            "operaciones": self.operaciones,
            "iva": {
                "debito_fiscal": str(self.debito_fiscal),
                "credito_fiscal": str(self.credito_fiscal),
                "determinado": str(self.iva_determinado),
                "retenciones_sufridas": str(self.retenciones_iva_sufridas),
                "a_ingresar": str(self.iva_a_ingresar),
                "por_tratamiento": {
                    k: {kk: str(vv) for kk, vv in v.items()}
                    for k, v in self.por_tratamiento.items()
                },
            },
            "iibb": {
                "determinado": str(self.iibb_determinado),
                "retenciones_sufridas": str(self.retenciones_iibb_sufridas),
                "a_ingresar": str(self.iibb_a_ingresar),
                "por_jurisdiccion": {
                    k: {kk: str(vv) if isinstance(vv, Decimal) else vv for kk, vv in v.items()}
                    for k, v in self.iibb_por_jurisdiccion.items()
                },
            },
            "ganancias": {"retenciones_sufridas": str(self.retenciones_ganancias_sufridas)},
            "resumen": {
                "retribucion_bruta": str(self.retribucion_bruta),
                "carga_total": str(self.carga_total),
                "margen_neto": str(self.margen_neto),
                "presion_fiscal_pct": str(self.presion_fiscal_pct),
            },
            "control": {
                "diferencias_detectadas": self.diferencias_detectadas,
                "diferencias_altas": self.diferencias_altas,
                "importe_en_disputa": str(self.importe_en_disputa),
            },
            "avisos": self.avisos,
        }


def armar_posicion(
    conciliaciones: list[Conciliacion],
    periodo: str = "",
    params: ParametrosFiscales | None = None,
) -> PosicionFiscal:
    """Consolida varias liquidaciones conciliadas en la posicion del periodo."""
    params = params or cargar_parametros()
    posicion = PosicionFiscal(periodo=periodo)
    avisos: list[str] = []

    for conciliacion in conciliaciones:
        liquidacion = conciliacion.liquidacion
        posicion.liquidaciones.append(
            liquidacion.numero or liquidacion.mayorista or liquidacion.archivo_origen
        )

        totales = conciliacion.impuestos.get("totales", {})
        posicion.operaciones += int(totales.get("operaciones", 0))
        posicion.debito_fiscal += dec(totales.get("debito_fiscal", CERO))
        posicion.credito_fiscal += dec(totales.get("credito_fiscal", CERO))
        posicion.retribucion_bruta += dec(totales.get("retribucion_bruta", CERO))

        for tratamiento, valores in conciliacion.impuestos.get("por_tratamiento_iva", {}).items():
            acumulado = posicion.por_tratamiento.setdefault(
                tratamiento, {"base": CERO, "impuesto": CERO}
            )
            acumulado["base"] += dec(valores.get("base", CERO))
            acumulado["impuesto"] += dec(valores.get("impuesto", CERO))

        for codigo, valores in conciliacion.impuestos.get("por_jurisdiccion", {}).items():
            acumulado = posicion.iibb_por_jurisdiccion.setdefault(
                codigo,
                {"etiqueta": valores.get("etiqueta", codigo), "base": CERO, "impuesto": CERO},
            )
            acumulado["base"] += dec(valores.get("base", CERO))
            acumulado["impuesto"] += dec(valores.get("impuesto", CERO))

        # Lo efectivamente retenido es lo que se computa como pago a cuenta.
        for retencion in conciliacion.retenciones.get("detalle", []):
            informado = dec(retencion.get("informado", CERO))
            codigo = retencion.get("codigo", "")
            if codigo == "IVA_RG2854":
                posicion.retenciones_iva_sufridas += informado
            elif codigo == "IIBB_SIRCAR":
                posicion.retenciones_iibb_sufridas += informado
            elif codigo == "GANANCIAS_RG830":
                posicion.retenciones_ganancias_sufridas += informado

        posicion.diferencias_detectadas += len(conciliacion.diferencias)
        posicion.diferencias_altas += len(conciliacion.diferencias_altas)
        posicion.importe_en_disputa += sum(
            (abs(d.importe) for d in conciliacion.diferencias), CERO
        )
        avisos.extend(a for a in conciliacion.avisos if a not in avisos)

    for campo in (
        "debito_fiscal", "credito_fiscal", "retribucion_bruta",
        "retenciones_iva_sufridas", "retenciones_iibb_sufridas",
        "retenciones_ganancias_sufridas", "importe_en_disputa",
    ):
        setattr(posicion, campo, redondear(getattr(posicion, campo)))

    for valores in posicion.por_tratamiento.values():
        valores["base"] = redondear(valores["base"])
        valores["impuesto"] = redondear(valores["impuesto"])
    for valores in posicion.iibb_por_jurisdiccion.values():
        valores["base"] = redondear(valores["base"])
        valores["impuesto"] = redondear(valores["impuesto"])

    if posicion.iva_a_ingresar < CERO:
        avisos.append(
            "Las retenciones de IVA sufridas superan el debito del periodo: "
            "queda saldo a favor para trasladar."
        )
    if posicion.iibb_a_ingresar < CERO:
        avisos.append(
            "Las retenciones de Ingresos Brutos superan el impuesto determinado: "
            "queda saldo a favor. Si se repite, conviene pedir un certificado de "
            "no retencion."
        )

    posicion.avisos = avisos
    return posicion

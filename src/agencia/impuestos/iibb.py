"""Calculo de Ingresos Brutos.

Dos decisiones definen el impuesto:
  1. La base imponible. El intermediario tributa sobre la comision; en algunas
     jurisdicciones las agencias de turismo usan la base especial de
     "diferencia entre precio de venta y precio de compra".
  2. El reparto entre jurisdicciones. Si la agencia opera en varias provincias
     bajo Convenio Multilateral, la base se distribuye por el coeficiente
     unificado de cada una.
"""

from __future__ import annotations

from decimal import Decimal

from ..config import ParametrosFiscales
from ..dinero import CERO, dec, pct, redondear
from ..dominio import BaseIIBB, RolAgencia
from .modelos import DistribucionIIBB, OperacionGravada

REGIMEN_CONVENIO = "CONVENIO_MULTILATERAL"


def calcular_iibb(
    operacion: OperacionGravada, params: ParametrosFiscales
) -> tuple[Decimal, BaseIIBB, Decimal, list[DistribucionIIBB], list[str]]:
    """Devuelve (base, tipo_base, impuesto_total, distribucion, observaciones)."""
    servicio = params.servicio(operacion.tipo_servicio)
    observaciones: list[str] = []

    codigo_jurisdiccion = operacion.jurisdiccion or params.jurisdiccion_sede
    jurisdiccion = params.jurisdiccion(codigo_jurisdiccion)

    tipo_base = (
        operacion.base_iibb_forzada
        or _base_segun_rol(operacion, servicio.iibb_base, jurisdiccion.base_default)
    )
    base = _importe_base(operacion, tipo_base)

    if base < CERO:
        observaciones.append(
            "La base de Ingresos Brutos dio negativa (el costo supera al precio de venta). "
            "Se toma cero: el quebranto no genera impuesto pero conviene revisar la carga."
        )
        base = CERO

    distribucion = _distribuir(base, params, codigo_jurisdiccion, observaciones)
    total = redondear(sum((d.impuesto for d in distribucion), CERO))

    return base, tipo_base, total, distribucion, observaciones


def _base_segun_rol(
    operacion: OperacionGravada, base_servicio: BaseIIBB, base_jurisdiccion: BaseIIBB
) -> BaseIIBB:
    """El rol manda sobre la configuracion: el organizador nunca tributa por comision."""
    if operacion.rol is RolAgencia.ORGANIZADOR:
        if base_servicio is BaseIIBB.COMISION:
            return BaseIIBB.TOTAL
        return base_servicio
    if base_servicio is BaseIIBB.COMISION and base_jurisdiccion is BaseIIBB.DIFERENCIA:
        # La jurisdiccion preve base especial para agencias de turismo.
        return BaseIIBB.DIFERENCIA
    return base_servicio


def _importe_base(operacion: OperacionGravada, tipo: BaseIIBB) -> Decimal:
    if tipo is BaseIIBB.COMISION:
        return operacion.retribucion_agencia
    if tipo is BaseIIBB.DIFERENCIA:
        return redondear(operacion.precio_venta_neto - operacion.costo_neto + operacion.comision)
    return redondear(operacion.precio_venta_neto)


def _distribuir(
    base: Decimal,
    params: ParametrosFiscales,
    codigo_jurisdiccion: str,
    observaciones: list[str],
) -> list[DistribucionIIBB]:
    """Aplica el coeficiente unificado si corresponde Convenio Multilateral."""
    if params.regimen_iibb != REGIMEN_CONVENIO:
        jurisdiccion = params.jurisdiccion(codigo_jurisdiccion)
        return [_linea(jurisdiccion, base, Decimal("1"))]

    coeficientes = {
        codigo: cfg.coeficiente_unificado
        for codigo, cfg in params.jurisdicciones.items()
        if cfg.coeficiente_unificado > CERO
    }
    suma = sum(coeficientes.values(), CERO)

    if not coeficientes:
        jurisdiccion = params.jurisdiccion(codigo_jurisdiccion)
        observaciones.append(
            "No hay coeficientes de Convenio Multilateral cargados: se asigna el total "
            f"a {jurisdiccion.etiqueta}."
        )
        return [_linea(jurisdiccion, base, Decimal("1"))]

    if abs(suma - Decimal("1")) > Decimal("0.0001"):
        observaciones.append(
            f"Los coeficientes unificados suman {suma}, no 1,0000. Revisar el CM 05 "
            "en config/parametros_fiscales.json."
        )

    lineas = []
    for codigo, coeficiente in sorted(coeficientes.items()):
        jurisdiccion = params.jurisdiccion(codigo)
        lineas.append(_linea(jurisdiccion, redondear(base * coeficiente), coeficiente))
    return lineas


def _linea(jurisdiccion, base: Decimal, coeficiente: Decimal) -> DistribucionIIBB:
    return DistribucionIIBB(
        jurisdiccion=jurisdiccion.codigo,
        etiqueta=jurisdiccion.etiqueta,
        base=redondear(base),
        coeficiente=dec(coeficiente),
        alicuota=jurisdiccion.alicuota,
        impuesto=pct(base, jurisdiccion.alicuota),
    )

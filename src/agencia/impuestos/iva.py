"""Calculo del IVA de una operacion de agencia de viajes.

La regla que ordena todo: la agencia que actua por cuenta y orden de terceros
tributa sobre su retribucion (comision, over y fee), no sobre el total del
servicio. La agencia que organiza el viaje por cuenta propia factura el total
y computa el credito fiscal de sus compras.
"""

from __future__ import annotations

from decimal import Decimal

from ..config import ParametrosFiscales
from ..dinero import CERO, pct, redondear
from ..dominio import RolAgencia, TratamientoIVA
from .modelos import DesgloseIVA, OperacionGravada

FEE_SIEMPRE_GRAVADO = "FEE_AGENCIA"


def calcular_iva(
    operacion: OperacionGravada, params: ParametrosFiscales
) -> tuple[list[DesgloseIVA], Decimal, Decimal, list[str]]:
    """Devuelve (desglose, debito_fiscal, credito_fiscal, observaciones)."""
    servicio = params.servicio(operacion.tipo_servicio)
    desglose: list[DesgloseIVA] = []
    observaciones: list[str] = []

    if operacion.rol is RolAgencia.INTERMEDIARIO:
        _iva_intermediario(operacion, params, servicio, desglose, observaciones)
        credito = CERO
        if operacion.iva_credito_proveedor > CERO:
            observaciones.append(
                "Como intermediario no se computa el IVA de la factura del proveedor: "
                "ese credito pertenece al pasajero, que es el destinatario del servicio."
            )
    else:
        _iva_organizador(operacion, params, servicio, desglose, observaciones)
        credito = redondear(operacion.iva_credito_proveedor)

    debito = redondear(sum((d.impuesto for d in desglose), CERO))

    if servicio.nota:
        observaciones.append(f"{servicio.etiqueta}: {servicio.nota}")

    return desglose, debito, credito, observaciones


def _iva_intermediario(operacion, params, servicio, desglose, observaciones) -> None:
    """Grava la retribucion de la agencia con el tratamiento del servicio intermediado."""
    retribucion_servicio = redondear(operacion.comision + operacion.over)

    if retribucion_servicio != CERO:
        desglose.append(
            _linea(
                params,
                servicio.iva_comision,
                "Comision y over por intermediacion",
                retribucion_servicio,
            )
        )
        if servicio.iva_comision in (TratamientoIVA.EXENTO, TratamientoIVA.NO_GRAVADO):
            observaciones.append(
                f"La retribucion por {servicio.etiqueta.lower()} no genera debito fiscal "
                f"({params.etiqueta_iva(servicio.iva_comision)}). Igual se factura y se "
                "declara como operacion no gravada o exenta."
            )

    if operacion.fee != CERO:
        fee_cfg = params.servicio(FEE_SIEMPRE_GRAVADO)
        desglose.append(
            _linea(params, fee_cfg.iva_servicio, "Fee de gestion de la agencia", operacion.fee)
        )


def _iva_organizador(operacion, params, servicio, desglose, observaciones) -> None:
    """Grava el precio de venta total con el tratamiento del propio servicio."""
    base = operacion.precio_venta_neto
    if base != CERO:
        desglose.append(
            _linea(params, servicio.iva_servicio, "Venta de servicio propio", base)
        )
    if servicio.iva_servicio is TratamientoIVA.NO_GRAVADO and operacion.iva_credito_proveedor > CERO:
        observaciones.append(
            "El servicio vendido no esta alcanzado por el IVA: revisar si corresponde "
            "computar el credito fiscal de la compra o si debe prorratearse."
        )


def _linea(
    params: ParametrosFiscales, tratamiento: TratamientoIVA, concepto: str, base: Decimal
) -> DesgloseIVA:
    alicuota = params.alicuota_iva(tratamiento)
    impuesto = pct(base, alicuota) if params.computa_debito(tratamiento) else CERO
    return DesgloseIVA(
        tratamiento=tratamiento,
        concepto=concepto,
        base=redondear(base),
        alicuota=alicuota,
        impuesto=impuesto,
    )


def neto_desde_total(total: Decimal, alicuota: Decimal) -> Decimal:
    """Desagrega el neto de un importe que ya incluye IVA."""
    from ..dinero import CIEN, dec

    return redondear(dec(total) / (1 + dec(alicuota) / CIEN))


def iva_contenido(total: Decimal, alicuota: Decimal) -> Decimal:
    """IVA contenido en un importe final."""
    from ..dinero import dec

    return redondear(dec(total) - neto_desde_total(total, alicuota))

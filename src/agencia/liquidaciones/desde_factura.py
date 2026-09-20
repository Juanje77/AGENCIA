"""Convierte una factura de mayorista en una liquidacion conciliable.

La factura trae los totales; el sistema los reparte entre los conceptos del
detalle, deduce el tratamiento fiscal de cada uno y despues compara: si el
mayorista facturo IVA sobre una comision exenta, o dejo sin gravar una que
correspondia, la diferencia aparece.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ..config import ParametrosFiscales, cargar_parametros
from ..dinero import CERO, dec, redondear
from ..dominio import Moneda, TratamientoIVA
from .factura import Comprobante, leer_factura
from .modelos import LineaLiquidacion, Liquidacion
from .normalizador import inferir_tipo_servicio


def importar_factura(
    ruta: str | Path,
    cuit_agencia: str = "",
    mayorista: str = "",
    periodo: str = "",
    params: ParametrosFiscales | None = None,
    tipo_servicio_default: str = "OTRO",
) -> Liquidacion:
    """Lee una factura PDF y la deja lista para conciliar."""
    comprobante = leer_factura(ruta, cuit_agencia=cuit_agencia)
    return comprobante_a_liquidacion(
        comprobante, mayorista=mayorista, periodo=periodo, params=params,
        tipo_servicio_default=tipo_servicio_default,
    )


def comprobante_a_liquidacion(
    comprobante: Comprobante,
    mayorista: str = "",
    periodo: str = "",
    params: ParametrosFiscales | None = None,
    tipo_servicio_default: str = "OTRO",
) -> Liquidacion:
    params = params or cargar_parametros()
    signo = comprobante.signo

    liquidacion = Liquidacion(
        mayorista=mayorista or comprobante.razon_social_emisor,
        numero=comprobante.identificacion,
        periodo=periodo or comprobante.periodo or comprobante.fecha_emision,
        fecha=comprobante.fecha_emision,
        archivo_origen=comprobante.archivo,
        perfil_usado="factura-pdf",
        moneda=Moneda(comprobante.moneda),
        tipo_cambio=comprobante.tipo_cambio,
        avisos=list(comprobante.avisos),
    )
    liquidacion.comprobante = comprobante

    conceptos = comprobante.conceptos
    if not conceptos:
        liquidacion.avisos.append(
            "La factura no trae detalle legible: se toma el total como un unico "
            "concepto. El tratamiento fiscal por servicio no se puede verificar."
        )
        liquidacion.lineas.append(
            _linea_unica(comprobante, signo, tipo_servicio_default)
        )
        _repartir_percepcion(liquidacion, comprobante, signo)
        return liquidacion

    lineas: list[LineaLiquidacion] = []
    for numero, concepto in enumerate(conceptos, start=1):
        tipo = inferir_tipo_servicio(
            concepto.descripcion, default=tipo_servicio_default
        )
        lineas.append(
            LineaLiquidacion(
                referencia=concepto.codigo or f"{comprobante.identificacion} #{numero}",
                fecha=comprobante.fecha_emision,
                proveedor=comprobante.razon_social_emisor,
                servicio_descripcion=concepto.descripcion,
                tipo_servicio=tipo,
                moneda=Moneda(comprobante.moneda),
                tipo_cambio=comprobante.tipo_cambio,
                comision=redondear(concepto.importe * signo),
                importe_total=redondear(concepto.importe * signo),
                fila=numero,
                crudo=concepto.a_dict(),
            )
        )

    _repartir_iva(lineas, comprobante, params, signo)
    liquidacion.lineas = lineas
    _repartir_percepcion(liquidacion, comprobante, signo)
    return liquidacion


def _linea_unica(
    comprobante: Comprobante, signo: int, tipo_default: str
) -> LineaLiquidacion:
    neto = redondear(
        (comprobante.neto_total + comprobante.no_gravado + comprobante.exento) * signo
    )
    if neto == CERO:
        neto = redondear((comprobante.total - comprobante.iva_total) * signo)
    return LineaLiquidacion(
        referencia=comprobante.identificacion,
        fecha=comprobante.fecha_emision,
        proveedor=comprobante.razon_social_emisor,
        servicio_descripcion=f"Total de {comprobante.identificacion}",
        tipo_servicio=tipo_default,
        moneda=Moneda(comprobante.moneda),
        tipo_cambio=comprobante.tipo_cambio,
        comision=neto,
        iva_comision=redondear(comprobante.iva_total * signo),
        importe_total=redondear(comprobante.total * signo),
        fila=1,
    )


def _repartir_iva(
    lineas: list[LineaLiquidacion],
    comprobante: Comprobante,
    params: ParametrosFiscales,
    signo: int,
) -> None:
    """Asigna el IVA facturado a los conceptos que segun su servicio lo llevan.

    Si ninguno deberia llevarlo pero la factura trae IVA, se reparte por
    importe: asi la diferencia queda a la vista en la conciliacion en vez de
    perderse.
    """
    iva_facturado = redondear(comprobante.iva_total * signo)
    if iva_facturado == CERO:
        return

    gravadas = [
        l for l in lineas
        if params.servicio(l.tipo_servicio).iva_comision
        not in (TratamientoIVA.EXENTO, TratamientoIVA.NO_GRAVADO, TratamientoIVA.EXPORTACION)
    ]
    destino = gravadas or lineas
    base = redondear(sum((l.comision for l in destino), CERO))

    if base == CERO:
        destino[0].iva_comision = iva_facturado
        return

    asignado = CERO
    for linea in destino[:-1]:
        parte = redondear(iva_facturado * linea.comision / base)
        linea.iva_comision = parte
        asignado += parte
    destino[-1].iva_comision = redondear(iva_facturado - asignado)

    if not gravadas:
        for linea in lineas:
            linea.avisos.append(
                "La factura trae IVA pero ningun concepto deberia llevarlo segun "
                "su tipo de servicio."
            )


def _repartir_percepcion(
    liquidacion: Liquidacion, comprobante: Comprobante, signo: int
) -> None:
    """La percepcion de Ingresos Brutos se prorratea entre los conceptos."""
    percepcion = redondear(
        (comprobante.percepcion_iibb or comprobante.otros_tributos) * signo
    )
    if percepcion == CERO or not liquidacion.lineas:
        return

    base = redondear(sum((l.comision for l in liquidacion.lineas), CERO))
    if base == CERO:
        liquidacion.lineas[0].ret_iibb = percepcion
        return

    asignado = CERO
    for linea in liquidacion.lineas[:-1]:
        parte = redondear(percepcion * linea.comision / base)
        linea.ret_iibb = parte
        asignado += parte
    liquidacion.lineas[-1].ret_iibb = redondear(percepcion - asignado)

    if comprobante.percepcion_iibb == CERO and comprobante.otros_tributos != CERO:
        liquidacion.avisos.append(
            "Se tomo 'Otros Tributos' como percepcion de Ingresos Brutos. "
            "Verifica el detalle de la factura."
        )

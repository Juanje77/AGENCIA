"""Orquestador del calculo fiscal de una operacion."""

from __future__ import annotations

from decimal import Decimal

from ..config import ParametrosFiscales, cargar_parametros
from ..dinero import CERO, redondear
from ..dominio import CondicionIVA, TratamientoIVA
from .iibb import calcular_iibb
from .iva import calcular_iva
from .modelos import OperacionGravada, ResultadoFiscal
from .retenciones import calcular_retenciones


def calcular_operacion(
    operacion: OperacionGravada,
    params: ParametrosFiscales | None = None,
    condicion: CondicionIVA = CondicionIVA.RESPONSABLE_INSCRIPTO,
    con_retenciones: bool = True,
) -> ResultadoFiscal:
    """Calcula IVA, Ingresos Brutos y retenciones de una linea de venta."""
    params = params or cargar_parametros()

    desglose, debito, credito, obs_iva = calcular_iva(operacion, params)
    base_iibb, tipo_base, iibb_total, distribucion, obs_iibb = calcular_iibb(operacion, params)

    resultado = ResultadoFiscal(
        operacion=operacion,
        desglose_iva=desglose,
        debito_fiscal=debito,
        credito_fiscal=credito,
        base_iibb=base_iibb,
        base_iibb_tipo=tipo_base,
        iibb_total=iibb_total,
        distribucion_iibb=distribucion,
        observaciones=obs_iva + obs_iibb,
    )

    if con_retenciones and operacion.comision > CERO:
        iva_de_la_comision = _iva_sobre_comision(resultado, operacion)
        resultado.retenciones = calcular_retenciones(
            params,
            comision_neta=operacion.comision,
            iva_comision=iva_de_la_comision,
            condicion=condicion,
        )

    return resultado


def _iva_sobre_comision(resultado: ResultadoFiscal, operacion: OperacionGravada) -> Decimal:
    """Aisla el IVA que corresponde a la comision (sin el over ni el fee)."""
    for linea in resultado.desglose_iva:
        if linea.concepto.startswith("Comision") and linea.base > CERO:
            proporcion = operacion.comision / linea.base
            return redondear(linea.impuesto * proporcion)
    return CERO


def calcular_lote(
    operaciones: list[OperacionGravada],
    params: ParametrosFiscales | None = None,
    condicion: CondicionIVA = CondicionIVA.RESPONSABLE_INSCRIPTO,
    con_retenciones: bool = True,
) -> list[ResultadoFiscal]:
    params = params or cargar_parametros()
    return [
        calcular_operacion(op, params, condicion, con_retenciones) for op in operaciones
    ]


def consolidar(resultados: list[ResultadoFiscal]) -> dict:
    """Suma un conjunto de resultados en los totales que se declaran."""
    totales = {
        "operaciones": len(resultados),
        "retribucion_bruta": CERO,
        "debito_fiscal": CERO,
        "credito_fiscal": CERO,
        "iva_a_pagar": CERO,
        "base_iibb": CERO,
        "iibb_total": CERO,
        "retenciones_totales": CERO,
        "carga_impositiva": CERO,
        "margen_neto": CERO,
    }
    por_tratamiento: dict[str, dict[str, Decimal]] = {}
    por_jurisdiccion: dict[str, dict[str, Decimal]] = {}
    por_retencion: dict[str, dict[str, Decimal]] = {}

    for r in resultados:
        totales["retribucion_bruta"] += r.retribucion_bruta
        totales["debito_fiscal"] += r.debito_fiscal
        totales["credito_fiscal"] += r.credito_fiscal
        totales["base_iibb"] += r.base_iibb
        totales["iibb_total"] += r.iibb_total
        totales["retenciones_totales"] += r.retenciones_totales

        for linea in r.desglose_iva:
            acumulado = por_tratamiento.setdefault(
                linea.tratamiento.value, {"base": CERO, "impuesto": CERO}
            )
            acumulado["base"] += linea.base
            acumulado["impuesto"] += linea.impuesto

        for d in r.distribucion_iibb:
            acumulado = por_jurisdiccion.setdefault(
                d.jurisdiccion, {"base": CERO, "impuesto": CERO, "etiqueta": d.etiqueta}
            )
            acumulado["base"] += d.base
            acumulado["impuesto"] += d.impuesto

        for ret in r.retenciones:
            if not ret.aplicada:
                continue
            acumulado = por_retencion.setdefault(
                ret.codigo, {"base": CERO, "importe": CERO, "etiqueta": ret.etiqueta}
            )
            acumulado["base"] += ret.base
            acumulado["importe"] += ret.importe

    totales["iva_a_pagar"] = totales["debito_fiscal"] - totales["credito_fiscal"]
    totales["carga_impositiva"] = totales["iva_a_pagar"] + totales["iibb_total"]
    totales["margen_neto"] = totales["retribucion_bruta"] - totales["carga_impositiva"]

    return {
        "totales": {k: redondear(v) if isinstance(v, Decimal) else v for k, v in totales.items()},
        "por_tratamiento_iva": {
            k: {kk: redondear(vv) for kk, vv in v.items()} for k, v in por_tratamiento.items()
        },
        "por_jurisdiccion": {
            k: {kk: (redondear(vv) if isinstance(vv, Decimal) else vv) for kk, vv in v.items()}
            for k, v in por_jurisdiccion.items()
        },
        "por_retencion": {
            k: {kk: (redondear(vv) if isinstance(vv, Decimal) else vv) for kk, vv in v.items()}
            for k, v in por_retencion.items()
        },
    }

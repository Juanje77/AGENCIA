"""Recalcula los impuestos de una liquidacion y la compara con lo informado.

El mayorista dice cuanto retuvo y cuanto IVA le corresponde a la comision.
Aca se recalcula todo de cero con los parametros de la agencia y se marcan las
diferencias, que es donde aparecen los errores de liquidacion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..config import ParametrosFiscales, cargar_parametros
from ..dinero import CERO, dec, dentro_de_tolerancia, redondear
from ..dominio import CondicionIVA, Moneda
from ..impuestos import OperacionGravada, ResultadoFiscal, calcular_operacion, consolidar
from .modelos import LineaLiquidacion, Liquidacion

ALTA, MEDIA, INFO = "ALTA", "MEDIA", "INFO"

# Una factura no lleva retenciones: esas se practican al pagar. Lo que si trae
# es la percepcion de Ingresos Brutos que le carga el mayorista.
REGIMENES_DE_FACTURA = ["PERCEPCION_IIBB_COMPROBANTE"]
REGIMENES_DE_PAGO = ["GANANCIAS_RG830", "IVA_RG2854", "IIBB_SIRCAR"]


@dataclass
class Diferencia:
    concepto: str
    informado: Decimal
    esperado: Decimal
    severidad: str = MEDIA
    referencia: str = ""
    fila: int = 0
    comentario: str = ""

    @property
    def importe(self) -> Decimal:
        return redondear(self.informado - self.esperado)

    def a_dict(self) -> dict:
        return {
            "concepto": self.concepto,
            "referencia": self.referencia,
            "fila": self.fila,
            "informado": str(self.informado),
            "esperado": str(self.esperado),
            "diferencia": str(self.importe),
            "severidad": self.severidad,
            "comentario": self.comentario,
        }


@dataclass
class LineaConciliada:
    linea: LineaLiquidacion
    fiscal: ResultadoFiscal | None = None
    diferencias: list[Diferencia] = field(default_factory=list)
    calculada: bool = True
    motivo_omision: str = ""

    @property
    def tiene_diferencias(self) -> bool:
        return any(d.severidad in (ALTA, MEDIA) for d in self.diferencias)

    def a_dict(self) -> dict:
        return {
            "linea": self.linea.a_dict(),
            "fiscal": self.fiscal.a_dict() if self.fiscal else None,
            "diferencias": [d.a_dict() for d in self.diferencias],
            "calculada": self.calculada,
            "motivo_omision": self.motivo_omision,
        }


@dataclass
class Conciliacion:
    liquidacion: Liquidacion
    lineas: list[LineaConciliada] = field(default_factory=list)
    impuestos: dict = field(default_factory=dict)
    retenciones: dict = field(default_factory=dict)
    diferencias: list[Diferencia] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def lineas_con_diferencias(self) -> list[LineaConciliada]:
        return [l for l in self.lineas if l.tiene_diferencias]

    @property
    def total_diferencias(self) -> Decimal:
        return redondear(sum((d.importe for d in self.diferencias), CERO))

    @property
    def diferencias_altas(self) -> list[Diferencia]:
        return [d for d in self.diferencias if d.severidad == ALTA]

    def a_dict(self) -> dict:
        return {
            "liquidacion": self.liquidacion.resumen(),
            "lineas": [l.a_dict() for l in self.lineas],
            "impuestos": _serializar(self.impuestos),
            "retenciones": _serializar(self.retenciones),
            "diferencias": [d.a_dict() for d in self.diferencias],
            "total_diferencias": str(self.total_diferencias),
            "cantidad_diferencias": len(self.diferencias),
            "diferencias_altas": len(self.diferencias_altas),
            "avisos": self.avisos,
        }


def conciliar(
    liquidacion: Liquidacion,
    params: ParametrosFiscales | None = None,
    condicion: CondicionIVA = CondicionIVA.RESPONSABLE_INSCRIPTO,
    cotizaciones: dict[str, Decimal] | None = None,
) -> Conciliacion:
    """Recalcula la liquidacion completa y lista las diferencias encontradas."""
    params = params or cargar_parametros()
    cotizaciones = {k: dec(v) for k, v in (cotizaciones or {}).items()}

    resultado = Conciliacion(liquidacion=liquidacion, avisos=list(liquidacion.avisos))
    fiscales: list[ResultadoFiscal] = []

    for linea in liquidacion.lineas:
        conciliada = _conciliar_linea(linea, params, condicion, cotizaciones)
        resultado.lineas.append(conciliada)
        if conciliada.fiscal is not None:
            fiscales.append(conciliada.fiscal)
        resultado.diferencias.extend(conciliada.diferencias)

    resultado.impuestos = consolidar(fiscales)
    resultado.retenciones, diferencias_del_pago = _conciliar_retenciones(
        liquidacion, resultado, params, condicion, cotizaciones
    )
    resultado.diferencias.extend(diferencias_del_pago)
    resultado.avisos.extend(params.advertencias_de_configuracion())

    omitidas = sum(1 for l in resultado.lineas if not l.calculada)
    if omitidas:
        resultado.avisos.append(
            f"{omitidas} linea(s) quedaron fuera del calculo por falta de datos. "
            "Revisalas en el detalle antes de declarar."
        )

    return resultado


def _conciliar_linea(
    linea: LineaLiquidacion,
    params: ParametrosFiscales,
    condicion: CondicionIVA,
    cotizaciones: dict[str, Decimal],
) -> LineaConciliada:
    conciliada = LineaConciliada(linea=linea)

    factor = _factor_a_pesos(linea, cotizaciones)
    if factor is None:
        conciliada.calculada = False
        conciliada.motivo_omision = (
            f"Falta el tipo de cambio de {linea.moneda.value} para la fila {linea.fila}."
        )
        return conciliada

    operacion = OperacionGravada(
        tipo_servicio=linea.tipo_servicio,
        rol=linea.rol,
        costo_neto=redondear(linea.costo_neto * factor),
        comision=redondear(linea.comision * factor),
        over=redondear(linea.over * factor),
        jurisdiccion=linea.jurisdiccion,
        descripcion=linea.servicio_descripcion or linea.referencia,
        referencia=linea.referencia,
        moneda_origen=linea.moneda,
        importe_origen=linea.importe_total,
    )

    fiscal = calcular_operacion(operacion, params, condicion, con_retenciones=False)
    conciliada.fiscal = fiscal
    conciliada.diferencias = _comparar(linea, fiscal, params, factor)
    return conciliada


def _factor_a_pesos(linea: LineaLiquidacion, cotizaciones: dict[str, Decimal]) -> Decimal | None:
    if linea.moneda is Moneda.ARS:
        return Decimal("1")
    if linea.tipo_cambio > CERO:
        return linea.tipo_cambio
    cotizacion = cotizaciones.get(linea.moneda.value, CERO)
    return cotizacion if cotizacion > CERO else None


def _comparar(
    linea: LineaLiquidacion,
    fiscal: ResultadoFiscal,
    params: ParametrosFiscales,
    factor: Decimal,
) -> list[Diferencia]:
    """Compara lo que informo el mayorista contra lo recalculado."""
    diferencias: list[Diferencia] = []
    tolerancia_abs = params.tolerancia_absoluta
    tolerancia_pct = params.tolerancia_pct

    def agregar(concepto, informado, esperado, severidad=MEDIA, comentario=""):
        informado, esperado = dec(informado), dec(esperado)
        if dentro_de_tolerancia(esperado, informado, tolerancia_abs, tolerancia_pct):
            return
        diferencias.append(
            Diferencia(
                concepto=concepto,
                informado=redondear(informado),
                esperado=redondear(esperado),
                severidad=severidad,
                referencia=linea.referencia,
                fila=linea.fila,
                comentario=comentario,
            )
        )

    # 1. Aritmetica interna de la liquidacion.
    if linea.importe_total != CERO and linea.costo_neto != CERO:
        agregar(
            "Importe total vs neto + comision",
            linea.importe_total,
            redondear(linea.costo_neto + linea.comision),
            MEDIA,
            "El total informado no coincide con la suma de neto y comision.",
        )

    # 2. IVA sobre la comision.
    iva_esperado = _iva_comision_esperado(fiscal, factor)
    if linea.iva_comision != CERO or iva_esperado != CERO:
        agregar(
            "IVA sobre comision",
            linea.iva_comision,
            iva_esperado,
            ALTA,
            f"Tratamiento aplicado: {params.servicio(linea.tipo_servicio).etiqueta}.",
        )

    # 3. Neto a cobrar.
    if linea.neto_a_cobrar != CERO:
        neto_esperado = redondear(
            linea.comision
            + linea.iva_comision
            - linea.ret_ganancias
            - linea.ret_iva
            - linea.ret_iibb
            - linea.otros_descuentos
        )
        agregar(
            "Neto a cobrar",
            linea.neto_a_cobrar,
            neto_esperado,
            MEDIA,
            "El neto liquidado no cierra con comision mas IVA menos retenciones.",
        )

    return diferencias


def _conciliar_retenciones(
    liquidacion: Liquidacion,
    resultado: Conciliacion,
    params: ParametrosFiscales,
    condicion: CondicionIVA,
    cotizaciones: dict[str, Decimal],
) -> tuple[dict, list[Diferencia]]:
    """Compara las retenciones del pago completo, que es como se practican.

    Los regimenes de retencion miran el pago, no la reserva: el minimo no
    sujeto de Ganancias se evalua una vez sobre el total liquidado, no reserva
    por reserva.
    """
    from ..impuestos import calcular_retenciones

    comision_neta = CERO
    iva_comision_esperado = CERO
    informado = {"GANANCIAS_RG830": CERO, "IVA_RG2854": CERO, "IIBB_SIRCAR": CERO}

    for conciliada in resultado.lineas:
        linea = conciliada.linea
        factor = _factor_a_pesos(linea, cotizaciones) or Decimal("1")
        informado["GANANCIAS_RG830"] += redondear(linea.ret_ganancias * factor)
        informado["IVA_RG2854"] += redondear(linea.ret_iva * factor)
        informado["IIBB_SIRCAR"] += redondear(linea.ret_iibb * factor)
        if conciliada.fiscal is None:
            continue
        comision_neta += conciliada.fiscal.operacion.comision
        iva_comision_esperado += _iva_comision_esperado(conciliada.fiscal, Decimal("1"))

    comprobante = getattr(liquidacion, "comprobante", None)
    if comprobante is not None:
        codigos = REGIMENES_DE_FACTURA
        neto_gravado = _neto_gravado_del_comprobante(comprobante)
        informado["PERCEPCION_IIBB_COMPROBANTE"] = informado.pop("IIBB_SIRCAR", CERO)
    else:
        codigos = REGIMENES_DE_PAGO
        neto_gravado = None

    esperadas = calcular_retenciones(
        params,
        comision_neta=redondear(comision_neta),
        iva_comision=redondear(iva_comision_esperado),
        condicion=condicion,
        solo_codigos=codigos,
        neto_gravado=neto_gravado,
    )

    diferencias: list[Diferencia] = []
    detalle = []
    for retencion in esperadas:
        total_informado = redondear(informado.get(retencion.codigo, CERO))
        detalle.append(
            {
                "codigo": retencion.codigo,
                "etiqueta": retencion.etiqueta,
                "base": retencion.base,
                "alicuota": retencion.alicuota,
                "esperado": retencion.importe,
                "informado": total_informado,
                "diferencia": redondear(total_informado - retencion.importe),
                "aplicada": retencion.aplicada,
                "motivo": retencion.motivo,
            }
        )
        if total_informado == CERO and retencion.importe == CERO:
            continue
        if dentro_de_tolerancia(
            retencion.importe, total_informado, params.tolerancia_absoluta, params.tolerancia_pct
        ):
            continue
        de_mas = total_informado > retencion.importe
        diferencias.append(
            Diferencia(
                concepto=f"{retencion.etiqueta} (total de la liquidacion)",
                informado=total_informado,
                esperado=retencion.importe,
                severidad=ALTA if de_mas else MEDIA,
                referencia=liquidacion.numero or liquidacion.mayorista,
                comentario=(
                    "Se retuvo de mas: reclamar la nota de credito o computar el "
                    "excedente como pago a cuenta."
                    if de_mas
                    else "Se retuvo de menos que lo calculado: verificar el certificado."
                ),
            )
        )

    resumen = {
        "base_comision_neta": redondear(comision_neta),
        "base_iva_comision": redondear(iva_comision_esperado),
        "detalle": detalle,
        "total_informado": redondear(sum(informado.values(), CERO)),
        "total_esperado": redondear(sum((r.importe for r in esperadas), CERO)),
    }
    return resumen, diferencias


def _neto_gravado_del_comprobante(comprobante) -> Decimal:
    """Base de la percepcion: lo gravado de la factura, no el total."""
    neto = dec(getattr(comprobante, "neto_total", CERO))
    return neto if neto != CERO else dec(getattr(comprobante, "total", CERO))


def _iva_comision_esperado(fiscal: ResultadoFiscal, factor: Decimal) -> Decimal:
    """IVA que corresponde a la comision, en la moneda original de la linea."""
    operacion = fiscal.operacion
    for desglose in fiscal.desglose_iva:
        if desglose.concepto.startswith("Comision") and desglose.base > CERO:
            proporcion = operacion.comision / desglose.base
            return redondear(desglose.impuesto * proporcion / factor)
    return CERO


def _serializar(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: _serializar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_serializar(v) for v in valor]
    return valor

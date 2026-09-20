"""Retenciones que el mayorista practica al liquidarle a la agencia.

El mayorista paga la comision neta de retenciones. Esas retenciones no son un
costo: son pagos a cuenta de Ganancias, IVA e Ingresos Brutos. El sistema las
recalcula para poder comparar lo retenido contra lo que correspondia.
"""

from __future__ import annotations

from decimal import Decimal

from ..config import ConfigRetencion, ParametrosFiscales
from ..dinero import CERO, dec, pct, redondear
from ..dominio import CondicionIVA
from .modelos import RetencionCalculada

MINIMO_DEDUCIBLE = "DEDUCIBLE"
MINIMO_UMBRAL = "UMBRAL"


def calcular_retenciones(
    params: ParametrosFiscales,
    comision_neta: Decimal,
    iva_comision: Decimal,
    condicion: CondicionIVA = CondicionIVA.RESPONSABLE_INSCRIPTO,
    acreditacion_bancaria: Decimal = CERO,
    solo_codigos: list[str] | None = None,
    neto_gravado: Decimal | None = None,
) -> list[RetencionCalculada]:
    """Calcula las retenciones y percepciones activas sobre la base que toque."""
    bases = {
        "COMISION_NETA": dec(comision_neta),
        "IVA_COMISION": dec(iva_comision),
        "ACREDITACION_BANCARIA": dec(acreditacion_bancaria),
        # Lo gravado es la base de las percepciones que vienen en la factura.
        "NETO_GRAVADO": dec(comision_neta if neto_gravado is None else neto_gravado),
    }

    resultados = []
    for codigo, cfg in params.retenciones.items():
        if solo_codigos is not None and codigo not in solo_codigos:
            continue
        if not cfg.activo:
            continue
        base_bruta = bases.get(cfg.aplica_sobre)
        if base_bruta is None:
            resultados.append(
                RetencionCalculada(
                    codigo=codigo,
                    etiqueta=cfg.etiqueta,
                    base=CERO,
                    alicuota=CERO,
                    importe=CERO,
                    aplicada=False,
                    motivo=f"Base desconocida: {cfg.aplica_sobre}",
                )
            )
            continue
        resultados.append(_una_retencion(codigo, cfg, base_bruta, condicion))
    return resultados


def _una_retencion(
    codigo: str, cfg: ConfigRetencion, base_bruta: Decimal, condicion: CondicionIVA
) -> RetencionCalculada:
    alicuota = (
        cfg.alicuota_inscripto
        if condicion is CondicionIVA.RESPONSABLE_INSCRIPTO
        else cfg.alicuota_no_inscripto
    )

    if base_bruta <= CERO:
        return RetencionCalculada(
            codigo, cfg.etiqueta, CERO, alicuota, CERO, False, "Sin base imponible"
        )

    if cfg.minimo_no_sujeto > CERO:
        if cfg.tipo_minimo == MINIMO_DEDUCIBLE:
            base = redondear(base_bruta - cfg.minimo_no_sujeto)
            if base <= CERO:
                return RetencionCalculada(
                    codigo,
                    cfg.etiqueta,
                    CERO,
                    alicuota,
                    CERO,
                    False,
                    f"No supera el minimo no sujeto a retencion ({cfg.minimo_no_sujeto})",
                )
        else:
            base = base_bruta
            if base_bruta < cfg.minimo_no_sujeto:
                return RetencionCalculada(
                    codigo,
                    cfg.etiqueta,
                    base_bruta,
                    alicuota,
                    CERO,
                    False,
                    f"Por debajo del importe minimo de retencion ({cfg.minimo_no_sujeto})",
                )
    else:
        base = base_bruta

    return RetencionCalculada(
        codigo=codigo,
        etiqueta=cfg.etiqueta,
        base=redondear(base),
        alicuota=alicuota,
        importe=pct(base, alicuota),
        aplicada=True,
    )

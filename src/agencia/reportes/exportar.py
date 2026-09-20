"""Exportacion a CSV para pasarle los datos al contador."""

from __future__ import annotations

import csv
from pathlib import Path

from ..dinero import CERO
from ..liquidaciones.conciliacion import Conciliacion
from .posicion_fiscal import PosicionFiscal

COLUMNAS_LINEAS = [
    "referencia", "fecha", "pasajero", "destino", "proveedor", "servicio",
    "tipo_servicio", "moneda", "tipo_cambio", "comision_origen", "comision_ars",
    "tratamiento_iva", "base_iva", "iva_debito", "base_iibb", "iibb",
    "margen_neto", "avisos",
]


def exportar_lineas(conciliacion: Conciliacion, destino: str | Path) -> Path:
    """Detalle reserva por reserva con el impuesto calculado."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh, delimiter=";")
        escritor.writerow(COLUMNAS_LINEAS)
        for c in conciliacion.lineas:
            l = c.linea
            f = c.fiscal
            tratamiento = ""
            if f and f.desglose_iva:
                tratamiento = "+".join(sorted({d.tratamiento.value for d in f.desglose_iva}))
            escritor.writerow([
                l.referencia, l.fecha, l.pasajero, l.destino, l.proveedor,
                l.servicio_descripcion, l.tipo_servicio, l.moneda.value, l.tipo_cambio,
                l.comision,
                f.operacion.comision if f else "",
                tratamiento,
                sum((d.base for d in f.desglose_iva), CERO) if f else "",
                f.debito_fiscal if f else "",
                f.base_iibb if f else "",
                f.iibb_total if f else "",
                f.margen_neto if f else "",
                " | ".join(l.avisos + ([c.motivo_omision] if c.motivo_omision else [])),
            ])
    return destino


def exportar_diferencias(conciliacion: Conciliacion, destino: str | Path) -> Path:
    """Listado de diferencias para reclamarle al mayorista."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh, delimiter=";")
        escritor.writerow(
            ["severidad", "referencia", "fila", "concepto", "liquidado",
             "calculado", "diferencia", "comentario"]
        )
        for d in conciliacion.diferencias:
            escritor.writerow([
                d.severidad, d.referencia, d.fila or "", d.concepto,
                d.informado, d.esperado, d.importe, d.comentario,
            ])
    return destino


def exportar_posicion(posicion: PosicionFiscal, destino: str | Path) -> Path:
    """Posicion de IVA e IIBB del periodo en formato plano."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh, delimiter=";")
        escritor.writerow(["concepto", "detalle", "base", "importe"])

        for tratamiento, valores in sorted(posicion.por_tratamiento.items()):
            escritor.writerow(["IVA", tratamiento, valores["base"], valores["impuesto"]])
        escritor.writerow(["IVA", "Debito fiscal", "", posicion.debito_fiscal])
        escritor.writerow(["IVA", "Credito fiscal", "", posicion.credito_fiscal])
        escritor.writerow(["IVA", "Retenciones sufridas", "", posicion.retenciones_iva_sufridas])
        escritor.writerow(["IVA", "Saldo a ingresar", "", posicion.iva_a_ingresar])

        for codigo, valores in sorted(posicion.iibb_por_jurisdiccion.items()):
            escritor.writerow(
                ["IIBB", valores.get("etiqueta", codigo), valores["base"], valores["impuesto"]]
            )
        escritor.writerow(
            ["IIBB", "Retenciones sufridas", "", posicion.retenciones_iibb_sufridas]
        )
        escritor.writerow(["IIBB", "Saldo a ingresar", "", posicion.iibb_a_ingresar])
        escritor.writerow(
            ["GANANCIAS", "Retenciones sufridas", "", posicion.retenciones_ganancias_sufridas]
        )
    return destino

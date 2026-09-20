"""Posicion fiscal del periodo y exportaciones."""

import csv
from decimal import Decimal as D

from agencia.liquidaciones import conciliar, importar_liquidacion
from agencia.reportes import (
    armar_posicion,
    exportar_diferencias,
    exportar_lineas,
    exportar_posicion,
    render_liquidacion,
    render_posicion,
)


def _conciliacion(ruta):
    return conciliar(importar_liquidacion(ruta, mayorista="Ola", periodo="2026-09"))


def test_la_posicion_suma_las_liquidaciones_del_periodo(liquidacion_ejemplo):
    una = _conciliacion(liquidacion_ejemplo)
    dos = armar_posicion([una, _conciliacion(liquidacion_ejemplo)], periodo="2026-09")
    sola = armar_posicion([una], periodo="2026-09")
    assert dos.operaciones == sola.operaciones * 2
    assert dos.debito_fiscal == sola.debito_fiscal * 2


def test_las_retenciones_sufridas_se_descuentan_del_saldo(liquidacion_ejemplo):
    posicion = armar_posicion([_conciliacion(liquidacion_ejemplo)], periodo="2026-09")
    assert posicion.retenciones_iva_sufridas > D("0")
    assert posicion.iva_a_ingresar == (
        posicion.iva_determinado - posicion.retenciones_iva_sufridas
    )


def test_computa_lo_retenido_y_no_lo_calculado(liquidacion_ejemplo):
    """Como pago a cuenta solo vale lo que figura en el certificado."""
    conciliacion = _conciliacion(liquidacion_ejemplo)
    posicion = armar_posicion([conciliacion], periodo="2026-09")
    informado = sum(
        D(str(r["informado"]))
        for r in conciliacion.retenciones["detalle"]
        if r["codigo"] == "IVA_RG2854"
    )
    assert posicion.retenciones_iva_sufridas == informado


def test_separa_la_base_por_tratamiento_de_iva(liquidacion_ejemplo):
    posicion = armar_posicion([_conciliacion(liquidacion_ejemplo)])
    assert "EXENTO" in posicion.por_tratamiento
    assert "GRAVADO_21" in posicion.por_tratamiento
    assert posicion.por_tratamiento["EXENTO"]["impuesto"] == D("0.00")


def test_saldo_a_favor_de_iibb_genera_aviso(liquidacion_ejemplo):
    posicion = armar_posicion([_conciliacion(liquidacion_ejemplo)])
    posicion.retenciones_iibb_sufridas = posicion.iibb_determinado + D("100000")
    assert posicion.iibb_a_ingresar < D("0")


def test_presion_fiscal_sobre_las_comisiones(liquidacion_ejemplo):
    posicion = armar_posicion([_conciliacion(liquidacion_ejemplo)])
    assert D("0") < posicion.presion_fiscal_pct < D("100")
    assert posicion.margen_neto == posicion.retribucion_bruta - posicion.carga_total


def test_exporta_el_detalle_por_reserva(liquidacion_ejemplo, tmp_path):
    conciliacion = _conciliacion(liquidacion_ejemplo)
    destino = exportar_lineas(conciliacion, tmp_path / "detalle.csv")
    with destino.open(encoding="utf-8-sig") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))
    assert len(filas) == 8
    assert filas[0]["referencia"] == "F-102345"
    assert filas[0]["tipo_servicio"] == "AEREO_INTERNACIONAL"


def test_exporta_las_diferencias_para_reclamar(liquidacion_ejemplo, tmp_path):
    conciliacion = _conciliacion(liquidacion_ejemplo)
    destino = exportar_diferencias(conciliacion, tmp_path / "dif.csv")
    with destino.open(encoding="utf-8-sig") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))
    assert len(filas) == len(conciliacion.diferencias)
    assert {"severidad", "concepto", "diferencia"} <= set(filas[0])


def test_exporta_la_posicion_del_periodo(liquidacion_ejemplo, tmp_path):
    posicion = armar_posicion([_conciliacion(liquidacion_ejemplo)], periodo="2026-09")
    destino = exportar_posicion(posicion, tmp_path / "pos.csv")
    contenido = destino.read_text(encoding="utf-8-sig")
    assert "Saldo a ingresar" in contenido
    assert "IIBB" in contenido


def test_el_informe_html_lista_las_diferencias(liquidacion_ejemplo):
    html = render_liquidacion(_conciliacion(liquidacion_ejemplo))
    assert "Diferencias a revisar" in html
    assert "F-102349" in html
    assert "Como se leyo el archivo" in html


def test_el_informe_de_posicion_muestra_los_dos_impuestos(liquidacion_ejemplo):
    posicion = armar_posicion([_conciliacion(liquidacion_ejemplo)], periodo="2026-09")
    html = render_posicion(posicion)
    assert "Impuesto al valor agregado" in html
    assert "Ingresos Brutos por jurisdiccion" in html
    assert "Retenciones sufridas" in html

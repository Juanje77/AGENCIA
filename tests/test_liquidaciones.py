"""Lectura, normalizacion y conciliacion de liquidaciones."""

from decimal import Decimal as D

import pytest

from agencia.dominio import Moneda
from agencia.liquidaciones import ErrorDeLectura, conciliar, importar_liquidacion
from agencia.liquidaciones.normalizador import (
    detectar_columnas,
    inferir_moneda,
    inferir_tipo_servicio,
    normalizar_texto,
)


# --- Deteccion de columnas ---------------------------------------------------

def test_reconoce_encabezados_con_tildes_y_puntuacion():
    encabezados = ["File", "Fecha Emisión", "Comisión", "IVA s/Comisión", "Ret. IIBB"]
    columnas, ignoradas = detectar_columnas(encabezados)
    assert columnas == {
        0: "referencia", 1: "fecha", 2: "comision",
        3: "iva_comision", 4: "ret_iibb",
    }
    assert ignoradas == []


def test_iva_comision_no_se_confunde_con_comision():
    """El encabezado mas especifico gana: si no, el IVA pisaria a la comision."""
    columnas, _ = detectar_columnas(["Comision", "IVA Comision"])
    assert columnas == {0: "comision", 1: "iva_comision"}


def test_columna_desconocida_se_reporta_en_vez_de_adivinarse():
    columnas, ignoradas = detectar_columnas(["Comision", "Codigo interno XYZ"])
    assert columnas == {0: "comision"}
    assert ignoradas == ["Codigo interno XYZ"]


def test_dos_columnas_para_el_mismo_campo_gana_la_mas_precisa():
    columnas, ignoradas = detectar_columnas(["Importe", "Importe Total"])
    assert columnas == {1: "importe_total"}
    assert ignoradas == ["Importe"]


def test_sigla_tc_se_reconoce():
    columnas, _ = detectar_columnas(["T.C."])
    assert columnas == {0: "tipo_cambio"}


def test_mapeo_manual_del_perfil_tiene_prioridad():
    columnas, _ = detectar_columnas(
        ["Comision", "Valor X"], mapeo_manual={"Valor X": "over"}
    )
    assert columnas == {0: "comision", 1: "over"}


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Aereo internacional EZE-MAD", "AEREO_INTERNACIONAL"),
        ("Vuelo de cabotaje AEP-BRC", "AEREO_CABOTAJE"),
        ("Hotel Melia Madrid 5 noches", "HOTELERIA_EXTERIOR"),
        ("Hoteleria nacional Bariloche", "HOTELERIA_NACIONAL"),
        ("Paquete Europa 15 dias", "PAQUETE_EXTERIOR"),
        ("Crucero MSC Caribe", "CRUCERO"),
        ("Asistencia al viajero", "ASISTENCIA_VIAJERO"),
        ("Seguro de cancelacion", "SEGURO"),
        ("Rent a car Miami", "ALQUILER_AUTO_EXTERIOR"),
        ("Fee de emision", "FEE_AGENCIA"),
        ("", "OTRO"),
        ("Concepto ininteligible", "OTRO"),
    ],
)
def test_infiere_el_tipo_de_servicio_desde_la_descripcion(texto, esperado):
    assert inferir_tipo_servicio(texto) == esperado


def test_el_mapeo_del_perfil_pisa_las_reglas_generales():
    assert inferir_tipo_servicio(
        "HTL Madrid", mapeo={"HTL": "HOTELERIA_NACIONAL"}
    ) == "HOTELERIA_NACIONAL"


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("USD", Moneda.USD), ("U$S", Moneda.USD), ("Dolares", Moneda.USD),
        ("ARS", Moneda.ARS), ("Pesos", Moneda.ARS), ("EUR", Moneda.EUR),
        ("", Moneda.ARS),
    ],
)
def test_infiere_la_moneda(texto, esperado):
    assert inferir_moneda(texto) is esperado


def test_normalizar_texto_saca_tildes_y_puntuacion():
    assert normalizar_texto("IVA s/Comisión") == "iva s comision"


# --- Importacion -------------------------------------------------------------

def test_importa_el_csv_de_ejemplo_completo(liquidacion_ejemplo):
    liquidacion = importar_liquidacion(
        liquidacion_ejemplo, mayorista="Ola", periodo="2026-09"
    )
    assert liquidacion.cantidad_lineas == 8
    assert len(liquidacion.columnas_detectadas) == 16
    assert liquidacion.columnas_ignoradas == []


def test_saltea_las_filas_de_titulo_del_archivo(liquidacion_ejemplo):
    """El archivo trae tres filas de membrete antes de la tabla."""
    liquidacion = importar_liquidacion(liquidacion_ejemplo)
    assert any("fila 4" in a for a in liquidacion.avisos)


def test_descarta_la_fila_de_totales(liquidacion_ejemplo):
    liquidacion = importar_liquidacion(liquidacion_ejemplo)
    assert all(l.referencia.startswith("F-") for l in liquidacion.lineas)


def test_lee_importes_en_formato_argentino(liquidacion_ejemplo):
    liquidacion = importar_liquidacion(liquidacion_ejemplo)
    hotel = next(l for l in liquidacion.lineas if l.referencia == "F-102347")
    assert hotel.importe_total == D("1980000.00")
    assert hotel.comision == D("198000.00")
    assert hotel.moneda is Moneda.ARS


def test_conserva_el_tipo_de_cambio_de_cada_linea(liquidacion_ejemplo):
    liquidacion = importar_liquidacion(liquidacion_ejemplo)
    miami = next(l for l in liquidacion.lineas if l.referencia == "F-102349")
    assert miami.moneda is Moneda.USD
    assert miami.tipo_cambio == D("1452.50")


def test_archivo_inexistente_da_error_claro():
    with pytest.raises(ErrorDeLectura, match="No existe el archivo"):
        importar_liquidacion("/tmp/no-existe-esto.csv")


def test_extension_no_soportada_sugiere_alternativas(tmp_path):
    archivo = tmp_path / "liquidacion.docx"
    archivo.write_text("x")
    with pytest.raises(ErrorDeLectura, match="Formatos soportados"):
        importar_liquidacion(archivo)


def test_xls_viejo_explica_como_convertirlo(tmp_path):
    archivo = tmp_path / "liquidacion.xls"
    archivo.write_text("x")
    with pytest.raises(ErrorDeLectura, match="guardalo como .xlsx"):
        importar_liquidacion(archivo)


def test_archivo_sin_encabezados_reconocibles(tmp_path):
    archivo = tmp_path / "raro.csv"
    archivo.write_text("aaa;bbb;ccc\n1;2;3\n", encoding="utf-8")
    with pytest.raises(ErrorDeLectura, match="No se encontro una fila de encabezados"):
        importar_liquidacion(archivo)


def test_deduce_el_costo_neto_si_falta(tmp_path):
    archivo = tmp_path / "parcial.csv"
    archivo.write_text(
        "File;Concepto;Importe Total;Comision\nF-1;Hotel Madrid;100000;10000\n",
        encoding="utf-8",
    )
    liquidacion = importar_liquidacion(archivo)
    linea = liquidacion.lineas[0]
    assert linea.costo_neto == D("90000.00")
    assert any("deducido" in a for a in linea.avisos)


def test_avisa_si_no_hay_columna_de_comision(tmp_path):
    archivo = tmp_path / "sin_comision.csv"
    archivo.write_text("File;Concepto;Importe Total\nF-1;Hotel;100000\n", encoding="utf-8")
    liquidacion = importar_liquidacion(archivo)
    assert any("columna de comision" in a for a in liquidacion.avisos)


def test_usa_el_perfil_del_mayorista(liquidacion_ejemplo):
    liquidacion = importar_liquidacion(liquidacion_ejemplo, perfil="ejemplo_csv")
    assert liquidacion.perfil_usado == "ejemplo_csv"
    assert liquidacion.cantidad_lineas == 8


def test_perfil_inexistente_lista_los_disponibles(liquidacion_ejemplo):
    with pytest.raises(FileNotFoundError, match="Disponibles"):
        importar_liquidacion(liquidacion_ejemplo, perfil="mayorista_fantasma")


# --- Conciliacion ------------------------------------------------------------

def test_detecta_iva_cobrado_sobre_una_comision_exenta(liquidacion_ejemplo):
    """El mayorista facturo IVA sobre un aereo internacional: no corresponde."""
    conciliacion = conciliar(importar_liquidacion(liquidacion_ejemplo))
    alta = [d for d in conciliacion.diferencias if d.severidad == "ALTA"]
    assert any(d.referencia == "F-102349" and "IVA" in d.concepto for d in alta)


def test_las_retenciones_se_comparan_sobre_el_pago_total(liquidacion_ejemplo):
    """RG 830 mira el pago completo: comparar reserva por reserva daria falsos positivos."""
    conciliacion = conciliar(importar_liquidacion(liquidacion_ejemplo))
    codigos = {r["codigo"] for r in conciliacion.retenciones["detalle"]}
    assert "GANANCIAS_RG830" in codigos
    por_linea = [d for d in conciliacion.diferencias if d.fila and "Ganancias" in d.concepto]
    assert por_linea == []


def test_calcula_iva_e_iibb_del_periodo(liquidacion_ejemplo):
    conciliacion = conciliar(importar_liquidacion(liquidacion_ejemplo))
    totales = conciliacion.impuestos["totales"]
    assert totales["operaciones"] == 8
    assert totales["debito_fiscal"] > D("0")
    assert totales["iibb_total"] > D("0")
    assert totales["margen_neto"] < totales["retribucion_bruta"]


def test_convierte_a_pesos_con_el_tipo_de_cambio_de_la_linea(liquidacion_ejemplo):
    conciliacion = conciliar(importar_liquidacion(liquidacion_ejemplo))
    madrid = next(c for c in conciliacion.lineas if c.linea.referencia == "F-102345")
    assert madrid.fiscal.operacion.comision == D("160950.00")  # 111 USD * 1450


def test_sin_tipo_de_cambio_la_linea_queda_fuera_y_se_avisa(tmp_path):
    archivo = tmp_path / "sin_tc.csv"
    archivo.write_text(
        "File;Concepto;Moneda;Importe Total;Comision\n"
        "F-1;Hotel Madrid;USD;1000;100\n",
        encoding="utf-8",
    )
    conciliacion = conciliar(importar_liquidacion(archivo))
    assert conciliacion.lineas[0].calculada is False
    assert "tipo de cambio" in conciliacion.lineas[0].motivo_omision
    assert any("quedaron fuera del calculo" in a for a in conciliacion.avisos)


def test_la_cotizacion_provista_cubre_lo_que_falta(tmp_path):
    archivo = tmp_path / "sin_tc.csv"
    archivo.write_text(
        "File;Concepto;Moneda;Importe Total;Comision\n"
        "F-1;Hotel Madrid;USD;1000;100\n",
        encoding="utf-8",
    )
    conciliacion = conciliar(
        importar_liquidacion(archivo), cotizaciones={"USD": D("1450")}
    )
    assert conciliacion.lineas[0].calculada is True
    assert conciliacion.lineas[0].fiscal.operacion.comision == D("145000.00")


def test_una_liquidacion_correcta_no_genera_diferencias(tmp_path, params):
    """Comision de hotel en el exterior con IVA 21% y sin retenciones: cierra."""
    archivo = tmp_path / "ok.csv"
    archivo.write_text(
        "File;Concepto;Importe Total;Neto Proveedor;Comision;IVA s/Comision\n"
        "F-1;Hotel Madrid;110000;100000;10000;2100\n",
        encoding="utf-8",
    )
    conciliacion = conciliar(importar_liquidacion(archivo))
    por_linea = [d for d in conciliacion.diferencias if d.fila]
    assert por_linea == []


def test_detecta_que_el_total_no_cierra_con_neto_mas_comision(tmp_path):
    archivo = tmp_path / "descuadre.csv"
    archivo.write_text(
        "File;Concepto;Importe Total;Neto Proveedor;Comision;IVA s/Comision\n"
        "F-1;Hotel Madrid;150000;100000;10000;2100\n",
        encoding="utf-8",
    )
    conciliacion = conciliar(importar_liquidacion(archivo))
    assert any("Importe total" in d.concepto for d in conciliacion.diferencias)

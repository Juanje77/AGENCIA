"""Lector de liquidaciones en Excel."""

from decimal import Decimal as D

import pytest

from agencia.liquidaciones import ErrorDeLectura, conciliar, importar_liquidacion

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl no esta instalado")


@pytest.fixture
def liquidacion_xlsx(tmp_path):
    """Una liquidacion con membrete arriba, como las reales."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Liquidacion"
    hoja.append(["MAYORISTA DEMO S.A."])
    hoja.append(["Periodo: 09/2026"])
    hoja.append([])
    hoja.append([
        "File", "Fecha", "Pasajero", "Concepto", "Moneda", "T.C.",
        "Importe Total", "Neto Proveedor", "Comision", "IVA s/Comision",
        "Ret. IIBB", "Neto a Cobrar",
    ])
    hoja.append([
        "F-001", "2026-09-01", "PEREZ JUAN", "Hotel Madrid 5 noches", "USD", 1450,
        1100, 1000, 100, 21, 2, 119,
    ])
    hoja.append([
        "F-002", "2026-09-02", "GOMEZ ANA", "Aereo internacional EZE-GRU", "USD", 1450,
        800, 760, 40, 0, 0.8, 39.2,
    ])
    hoja.append(["TOTALES", "", "", "", "", "", 1900, 1760, 140])
    destino = tmp_path / "liquidacion.xlsx"
    libro.save(destino)
    return destino


def test_lee_un_xlsx_con_membrete(liquidacion_xlsx):
    liquidacion = importar_liquidacion(liquidacion_xlsx, mayorista="Demo")
    assert liquidacion.cantidad_lineas == 2
    assert liquidacion.lineas[0].referencia == "F-001"


def test_interpreta_los_numeros_nativos_de_excel(liquidacion_xlsx):
    liquidacion = importar_liquidacion(liquidacion_xlsx)
    assert liquidacion.lineas[0].comision == D("100")
    assert liquidacion.lineas[0].tipo_cambio == D("1450")


def test_descarta_la_fila_de_totales(liquidacion_xlsx):
    liquidacion = importar_liquidacion(liquidacion_xlsx)
    assert [l.referencia for l in liquidacion.lineas] == ["F-001", "F-002"]


def test_concilia_y_convierte_a_pesos(liquidacion_xlsx):
    conciliacion = conciliar(importar_liquidacion(liquidacion_xlsx))
    hotel = conciliacion.lineas[0]
    assert hotel.fiscal.operacion.comision == D("145000.00")  # 100 USD x 1450
    assert hotel.fiscal.debito_fiscal == D("30450.00")        # 21%


def test_avisa_cuando_hay_varias_hojas(tmp_path):
    libro = openpyxl.Workbook()
    libro.active.append(["File", "Concepto", "Importe Total", "Comision"])
    libro.active.append(["F-1", "Hotel Madrid", 1000, 100])
    libro.create_sheet("Otra hoja")
    destino = tmp_path / "varias.xlsx"
    libro.save(destino)
    liquidacion = importar_liquidacion(destino)
    assert any("hojas" in a for a in liquidacion.avisos)


def test_elige_la_hoja_indicada_por_el_perfil(tmp_path):
    libro = openpyxl.Workbook()
    libro.active.title = "Resumen"
    libro.active.append(["Nada util aca"])
    detalle = libro.create_sheet("Detalle")
    detalle.append(["File", "Concepto", "Importe Total", "Comision"])
    detalle.append(["F-9", "Crucero MSC", 5000, 500])
    destino = tmp_path / "hojas.xlsx"
    libro.save(destino)
    liquidacion = importar_liquidacion(destino, perfil={"hoja": "Detalle", "formato": "excel"})
    assert liquidacion.lineas[0].referencia == "F-9"
    assert liquidacion.lineas[0].tipo_servicio == "CRUCERO"


def test_hoja_inexistente_avisa_y_usa_la_primera(tmp_path):
    libro = openpyxl.Workbook()
    libro.active.append(["File", "Concepto", "Importe Total", "Comision"])
    libro.active.append(["F-1", "Hotel", 1000, 100])
    destino = tmp_path / "hoja_mala.xlsx"
    libro.save(destino)
    liquidacion = importar_liquidacion(
        destino, perfil={"hoja": "No existe", "formato": "excel"}
    )
    assert any("no existe" in a for a in liquidacion.avisos)


def test_archivo_corrupto_da_error_claro(tmp_path):
    destino = tmp_path / "roto.xlsx"
    destino.write_bytes(b"esto no es un xlsx")
    with pytest.raises(ErrorDeLectura, match="No se pudo abrir"):
        importar_liquidacion(destino)

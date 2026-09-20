"""Lectura de facturas de mayoristas en PDF."""

from decimal import Decimal as D

import pytest

from agencia.liquidaciones import ErrorDeLectura
from agencia.liquidaciones.factura import COMPRA, VENTA, Comprobante, leer_factura, parsear
from agencia.liquidaciones.lectores.pdf_texto import DocumentoPDF, PaginaPDF, Palabra

pymupdf = pytest.importorskip("pymupdf", reason="PyMuPDF no esta instalado")


@pytest.fixture(scope="module")
def factura_vertical(raiz):
    return raiz / "ejemplos" / "factura_ola_A_00012345.pdf"


@pytest.fixture(scope="module")
def factura_horizontal(raiz):
    return raiz / "ejemplos" / "factura_pie_horizontal_USD.pdf"


# --- pie de totales en renglones ---------------------------------------------

def test_lee_una_factura_con_el_pie_vertical(factura_vertical):
    c = leer_factura(factura_vertical, cuit_agencia="30-71234567-9")
    assert c.clase == "FACTURA"
    assert c.letra == "A"
    assert c.punto_venta == "0003"
    assert c.numero == "00012345"
    assert c.total == D("712482.00")
    assert c.confiable


def test_separa_el_iva_del_neto(factura_vertical):
    c = leer_factura(factura_vertical, cuit_agencia="30-71234567-9")
    assert c.gravado_21 == D("448400.00")
    assert c.iva_21 == D("94164.00")
    assert c.no_gravado == D("160950.00")


def test_identifica_emisor_y_receptor_por_cuit(factura_vertical):
    c = leer_factura(factura_vertical, cuit_agencia="30-71234567-9")
    assert c.cuit_emisor == "30587203451"
    assert c.cuit_receptor == "30712345679"
    assert c.sentido == COMPRA
    assert "OLA" in c.razon_social_emisor


def test_lee_el_cae(factura_vertical):
    c = leer_factura(factura_vertical, cuit_agencia="30-71234567-9")
    assert c.cae == "76234598712345"
    assert c.vencimiento_cae == "10/10/2026"


def test_extrae_el_detalle(factura_vertical):
    c = leer_factura(factura_vertical, cuit_agencia="30-71234567-9")
    assert len(c.conceptos) == 3
    assert c.conceptos[0].importe == D("160950.00")


# --- pie de totales en columnas ----------------------------------------------

def test_lee_una_factura_con_el_pie_horizontal(factura_horizontal):
    """Las etiquetas van en un renglon y los importes en el siguiente."""
    c = leer_factura(factura_horizontal, cuit_agencia="27-12345678-9")
    assert c.exento == D("2418.50")
    assert c.no_gravado == D("29.01")
    assert c.total == D("2447.51")
    assert c.confiable


def test_las_columnas_que_no_se_usan_no_corren_el_resto(factura_horizontal):
    """Impuesto PAIS y las RG ocupan columna: si no se cuentan, Total se desfasa."""
    c = leer_factura(factura_horizontal, cuit_agencia="27-12345678-9")
    assert c.iva_21 == D("0.00")
    assert c.total == D("2447.51")


def test_lee_moneda_y_tipo_de_cambio(factura_horizontal):
    c = leer_factura(factura_horizontal, cuit_agencia="27-12345678-9")
    assert c.moneda == "USD"
    assert c.tipo_cambio == D("1512.00")


# --- clasificacion -----------------------------------------------------------

def test_lo_comisionable_es_el_servicio_y_lo_demas_no(factura_horizontal):
    """El aereo exento paga comision; las tasas no gravadas no."""
    c = leer_factura(factura_horizontal, cuit_agencia="27-12345678-9")
    assert c.comisionable == D("2418.50")
    assert c.no_comisionable == D("29.01")


def test_el_credito_fiscal_solo_sale_de_una_factura_a_recibida():
    c = Comprobante(letra="A", sentido=COMPRA, iva_21=D("1000"))
    assert c.credito_fiscal == D("1000")

    c.letra = "B"
    assert c.credito_fiscal == D("0")

    c.letra = "A"
    c.sentido = VENTA
    assert c.credito_fiscal == D("0")


def test_una_nota_de_credito_resta():
    assert Comprobante(clase="NOTA DE CREDITO").signo == -1
    assert Comprobante(clase="FACTURA").signo == 1


# --- controles ---------------------------------------------------------------

def _documento(lineas: list[str]) -> DocumentoPDF:
    """Arma un documento de prueba, un renglon por linea."""
    renglones = [
        [Palabra(texto=p, x=float(i * 70), y=float(n * 12))
         for i, p in enumerate(linea.split("|"))]
        for n, linea in enumerate(lineas)
    ]
    return DocumentoPDF(
        paginas=[PaginaPDF(numero=1, texto="\n".join(lineas), renglones=renglones)],
        motor="prueba",
    )


def test_lo_que_se_deduce_queda_marcado_como_no_confiable():
    """Imputar un faltante no puede hacer pasar por buena una lectura dudosa."""
    documento = _documento([
        "FACTURA A Cod. 01",
        "Punto de Venta: 0001 Comp. Nro: 00000001",
        "Importe Neto Gravado: $ 1000,00",
        "IVA 21%: $ 210,00",
        "Importe Total: $ 9999,00",
    ])
    c = parsear(documento, "prueba.pdf")
    assert c.deducido
    assert not c.confiable
    assert c.no_gravado == D("8789.00")
    assert any("Se imputo" in a for a in c.avisos)


def test_un_descuadre_que_no_se_puede_deducir_se_denuncia():
    """Con todos los componentes presentes, la diferencia es un error de lectura."""
    documento = _documento([
        "FACTURA A Cod. 01",
        "Importe Neto Gravado: $ 1000,00",
        "IVA 21%: $ 210,00",
        "Importe Neto No Gravado: $ 50,00",
        "Importe Exento: $ 25,00",
        "Importe Total: $ 9999,00",
    ])
    c = parsear(documento, "prueba.pdf")
    assert not c.confiable
    assert any("no cierran" in a for a in c.avisos)


def test_cuando_cierra_queda_confiable():
    documento = _documento([
        "FACTURA A Cod. 01",
        "Punto de Venta: 0001 Comp. Nro: 00000001",
        "Importe Neto Gravado: $ 1000,00",
        "IVA 21%: $ 210,00",
        "Importe Total: $ 1210,00",
        "CAE: 12345678901234",
    ])
    c = parsear(documento, "prueba.pdf")
    assert c.confiable
    assert c.avisos == []


def test_avisa_que_una_factura_b_no_da_credito():
    documento = _documento([
        "FACTURA B Cod. 06",
        "Punto de Venta: 0001 Comp. Nro: 00000001",
        "Importe Total: $ 1210,00",
        "CAE: 12345678901234",
    ])
    c = parsear(documento, "prueba.pdf")
    assert any("no viene discriminado" in a for a in c.avisos)


def test_avisa_si_el_cuit_de_la_agencia_no_aparece():
    documento = _documento([
        "FACTURA A Cod. 01",
        "CUIT: 30-11111111-1",
        "Importe Total: $ 100,00",
    ])
    c = parsear(documento, "prueba.pdf", cuit_agencia="27-99999999-9")
    assert any("no figura en el comprobante" in a for a in c.avisos)


def test_reconoce_una_factura_emitida_por_la_agencia():
    documento = _documento([
        "FACTURA A Cod. 01",
        "CUIT: 27-12877126-9",
        "CUIT: 30-11111111-1",
        "Importe Total: $ 100,00",
    ])
    c = parsear(documento, "prueba.pdf", cuit_agencia="27-12877126-9")
    assert c.sentido == VENTA


def test_un_pdf_sin_importes_no_pasa_por_factura():
    documento = _documento(["Esto es una carta", "Sin ningun dato fiscal"])
    with pytest.raises(ErrorDeLectura, match="no parece una factura"):
        parsear(documento, "carta.pdf")


def test_el_cae_no_se_confunde_con_un_importe():
    """Un CAE tiene 14 digitos: tomarlo como total seria un desastre."""
    documento = _documento([
        "FACTURA A Cod. 01",
        "Importe Neto Gravado: $ 1000,00",
        "IVA 21%: $ 210,00",
        "Importe Total: $ 1210,00",
        "CAE N 86294940206437",
    ])
    c = parsear(documento, "prueba.pdf")
    assert c.total == D("1210.00")
    assert c.cae == "86294940206437"


def test_deduce_las_bases_por_alicuota_desde_el_iva():
    """Cuando hay un solo neto y dos alicuotas, se separa por el IVA de cada una."""
    documento = _documento([
        "FACTURA A Cod. 01",
        "Importe Neto Gravado AR$ 1.080.749,58",
        "IVA 21% AR$ 80.003,40",
        "IVA 10.5% AR$ 73.477,01",
        "Importe TOTAL AR$ 1.234.229,99",
        "CAE: 12345678901234",
    ])
    c = parsear(documento, "prueba.pdf")
    assert c.gravado_21 == D("380968.57")
    assert c.gravado_105 == D("699781.05")
    assert c.confiable


def test_archivo_inexistente():
    with pytest.raises(ErrorDeLectura, match="No existe"):
        leer_factura("/tmp/no-existe-esta-factura.pdf")


def test_un_pdf_escaneado_explica_que_hacer(tmp_path):
    """Sin OCR disponible, el mensaje tiene que decir como resolverlo."""
    documento = pymupdf.open()
    pagina = documento.new_page(width=595, height=842)
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
    pixmap.clear_with(255)
    pagina.insert_image(pymupdf.Rect(50, 50, 250, 250), pixmap=pixmap)
    destino = tmp_path / "escaneada.pdf"
    documento.save(destino)
    documento.close()

    pytest.importorskip("pytesseract", reason="con OCR disponible el PDF se lee igual")
    with pytest.raises(ErrorDeLectura) as exc:
        leer_factura(destino)
    assert "escaneada" in str(exc.value) or "OCR" in str(exc.value)

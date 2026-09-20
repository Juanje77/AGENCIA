"""Lectura de facturas con IA y la estrategia que decide cuando usarla.

El cliente del modelo se simula: los tests verifican como se interpreta y se
controla la respuesta, no el modelo en si.
"""

import json
from dataclasses import dataclass
from decimal import Decimal as D

import pytest

from agencia.liquidaciones.factura import COMPRA, VENTA, leer_factura
from agencia.liquidaciones.lectura_ia import ErrorDeIA, leer_con_ia


# --- cliente simulado --------------------------------------------------------

@dataclass
class _Bloque:
    text: str
    type: str = "text"


@dataclass
class _Respuesta:
    content: list
    stop_reason: str = "end_turn"


class ClienteFalso:
    """Devuelve lo que se le indique y registra como fue llamado."""

    def __init__(self, datos=None, stop_reason="end_turn", excepcion=None):
        self.datos = datos
        self.stop_reason = stop_reason
        self.excepcion = excepcion
        self.llamadas = []
        self.messages = self

    def create(self, **kwargs):
        self.llamadas.append(kwargs)
        if self.excepcion:
            raise self.excepcion
        cuerpo = self.datos if isinstance(self.datos, str) else json.dumps(self.datos)
        return _Respuesta([_Bloque(cuerpo)], self.stop_reason)


def _factura_valida(**cambios):
    """Una factura que cierra: 1000 + 210 + 50 = 1260."""
    datos = {
        "clase": "FACTURA", "letra": "A", "punto_venta": "3", "numero": "12345",
        "fecha_emision": "30/09/2026", "periodo": "",
        "cuit_emisor": "30587203451", "razon_social_emisor": "OLA S.A.",
        "cuit_receptor": "27128771269", "razon_social_receptor": "AGENCIA",
        "moneda": "ARS", "tipo_cambio": "0",
        "gravado_21": "1000.00", "gravado_105": "0", "iva_21": "210.00",
        "iva_105": "0", "iva_27": "0", "no_gravado": "50.00", "exento": "0",
        "percepcion_iibb": "0", "otros_tributos": "0", "total": "1260.00",
        "referencia": "F-1", "pasajeros": "PEREZ JUAN",
        "cae": "12345678901234", "vencimiento_cae": "10/10/2026",
        "conceptos": [{"codigo": "F-1", "descripcion": "Hotel", "importe": "1050.00"}],
        "observaciones": "",
    }
    datos.update(cambios)
    return datos


@pytest.fixture
def pdf(raiz):
    return raiz / "ejemplos" / "factura_ola_A_00012345.pdf"


# --- interpretacion de la respuesta ------------------------------------------

def test_arma_el_comprobante_desde_la_respuesta(pdf):
    cliente = ClienteFalso(_factura_valida())
    c = leer_con_ia(pdf, cuit_agencia="27-12877126-9", cliente=cliente)

    assert c.identificacion == "FACTURA A 0003-00012345"
    assert c.gravado_21 == D("1000.00")
    assert c.iva_21 == D("210.00")
    assert c.total == D("1260.00")
    assert c.cae == "12345678901234"
    assert c.pasajeros == "PEREZ JUAN"


def test_rellena_el_punto_de_venta_y_el_numero(pdf):
    c = leer_con_ia(pdf, cliente=ClienteFalso(_factura_valida()))
    assert c.punto_venta == "0003"
    assert c.numero == "00012345"


def test_reconoce_el_sentido_por_cuit(pdf):
    cliente = ClienteFalso(_factura_valida())
    assert leer_con_ia(pdf, cuit_agencia="27-12877126-9", cliente=cliente).sentido == COMPRA

    cliente = ClienteFalso(_factura_valida())
    assert leer_con_ia(pdf, cuit_agencia="30-58720345-1", cliente=cliente).sentido == VENTA


def test_avisa_si_el_cuit_de_la_agencia_no_aparece(pdf):
    c = leer_con_ia(pdf, cuit_agencia="20-99999999-9", cliente=ClienteFalso(_factura_valida()))
    assert any("no figura en el comprobante" in a for a in c.avisos)


def test_manda_el_pdf_y_pide_json(pdf):
    cliente = ClienteFalso(_factura_valida())
    leer_con_ia(pdf, cliente=cliente)

    enviado = cliente.llamadas[0]
    documento = enviado["messages"][0]["content"][0]
    assert documento["type"] == "document"
    assert documento["source"]["media_type"] == "application/pdf"
    assert enviado["output_config"]["format"]["type"] == "json_schema"


# --- el control aritmetico tambien se le aplica a la IA ----------------------

def test_una_lectura_que_no_cierra_queda_marcada(pdf):
    """El modelo puede equivocarse en un digito: el control lo detecta."""
    cliente = ClienteFalso(_factura_valida(total="9999.00"))
    c = leer_con_ia(pdf, cliente=cliente)
    assert not c.confiable
    assert any("no cierran" in a or "Se imputo" in a for a in c.avisos)


def test_siempre_avisa_que_la_leyo_un_modelo(pdf):
    c = leer_con_ia(pdf, cliente=ClienteFalso(_factura_valida()))
    assert "modelo de lenguaje" in c.avisos[0]
    assert c.motor_pdf.startswith("ia:")


def test_las_dudas_del_modelo_bajan_la_confianza(pdf):
    cliente = ClienteFalso(_factura_valida(observaciones="El total esta borroso."))
    c = leer_con_ia(pdf, cliente=cliente)
    assert not c.confiable
    assert any("borroso" in a for a in c.avisos)


# --- errores -----------------------------------------------------------------

def test_una_respuesta_que_no_es_json_se_denuncia(pdf):
    cliente = ClienteFalso("esto no es json")
    with pytest.raises(ErrorDeIA, match="no es JSON"):
        leer_con_ia(pdf, cliente=cliente)


def test_una_negativa_del_modelo_se_denuncia(pdf):
    cliente = ClienteFalso(_factura_valida(), stop_reason="refusal")
    with pytest.raises(ErrorDeIA, match="no quiso procesar"):
        leer_con_ia(pdf, cliente=cliente)


def test_un_archivo_muy_grande_no_se_manda(tmp_path):
    grande = tmp_path / "grande.pdf"
    grande.write_bytes(b"0" * (9 * 1024 * 1024))
    with pytest.raises(ErrorDeIA, match="limite"):
        leer_con_ia(grande, cliente=ClienteFalso(_factura_valida()))


def test_archivo_inexistente(tmp_path):
    with pytest.raises(ErrorDeIA, match="No existe"):
        leer_con_ia(tmp_path / "no-esta.pdf", cliente=ClienteFalso({}))


def test_los_errores_de_la_api_se_explican_en_castellano(pdf):
    class AuthenticationError(Exception):
        pass

    cliente = ClienteFalso(excepcion=AuthenticationError("401"))
    with pytest.raises(ErrorDeIA, match="credencial"):
        leer_con_ia(pdf, cliente=cliente)


def test_sin_credencial_explica_como_conseguirla(pdf, monkeypatch):
    pytest.importorskip("anthropic", reason="la libreria no esta instalada")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(ErrorDeIA, match="ANTHROPIC_API_KEY"):
        leer_con_ia(pdf)


# --- cuando se usa la IA y cuando no -----------------------------------------

def test_si_el_parser_acierta_no_se_gasta_en_ia(pdf, monkeypatch):
    """La factura de ejemplo cierra sola: la IA no tiene que intervenir."""
    llamado = []
    monkeypatch.setattr(
        "agencia.liquidaciones.lectura_ia.hay_ia", lambda: True
    )
    monkeypatch.setattr(
        "agencia.liquidaciones.lectura_ia.leer_con_ia",
        lambda *a, **k: llamado.append(1),
    )
    c = leer_factura(pdf, cuit_agencia="30-71234567-9")
    assert c.confiable
    assert c.motor_pdf == "pymupdf"
    assert llamado == []


def test_el_modo_nunca_no_llama_a_la_ia_aunque_falle(tmp_path, monkeypatch):
    from agencia.liquidaciones import ErrorDeLectura

    monkeypatch.setattr("agencia.liquidaciones.lectura_ia.hay_ia", lambda: True)
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"no soy un pdf")
    with pytest.raises(ErrorDeLectura):
        leer_factura(roto, usar_ia="nunca")


def test_sin_ia_configurada_el_parser_manda(pdf, monkeypatch):
    monkeypatch.setattr("agencia.liquidaciones.lectura_ia.hay_ia", lambda: False)
    c = leer_factura(pdf, cuit_agencia="30-71234567-9")
    assert c.motor_pdf == "pymupdf"


def test_el_modo_siempre_va_derecho_a_la_ia(pdf, monkeypatch):
    marca = []

    def falsa(ruta, cuit="", *a, **k):
        marca.append(ruta)
        from agencia.liquidaciones.factura import Comprobante
        return Comprobante(archivo="x", total=D("1"), motor_pdf="ia:falsa")

    monkeypatch.setattr("agencia.liquidaciones.lectura_ia.leer_con_ia", falsa)
    c = leer_factura(pdf, usar_ia="siempre")
    assert c.motor_pdf == "ia:falsa"
    assert len(marca) == 1

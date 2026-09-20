"""El adaptador WSGI y el modo sin disco, que es como corre en Vercel."""

import base64
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))


@pytest.fixture
def entorno_serverless(monkeypatch):
    """Simula el hosting: disco de solo lectura."""
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("AGENCIA_CLAVE", raising=False)
    monkeypatch.delenv("AGENCIA_SOLO_LECTURA", raising=False)


class _Silencioso(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def _levantar():
    from index import app

    servidor = make_server("127.0.0.1", 0, app, handler_class=_Silencioso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"


@pytest.fixture
def wsgi(entorno_serverless):
    servidor, base = _levantar()
    yield base
    servidor.shutdown()
    servidor.server_close()


def _get(base, ruta, cabeceras=None):
    peticion = urllib.request.Request(base + ruta, headers=cabeceras or {})
    with urllib.request.urlopen(peticion) as r:
        return r.status, r.read()


def _post(base, ruta, datos, cabeceras=None):
    peticion = urllib.request.Request(
        base + ruta,
        json.dumps(datos).encode(),
        {"Content-Type": "application/json", **(cabeceras or {})},
    )
    with urllib.request.urlopen(peticion) as r:
        return r.status, r.read()


# --- el adaptador sirve lo mismo que el servidor local -----------------------

def test_sirve_la_pagina(wsgi):
    codigo, cuerpo = _get(wsgi, "/")
    assert codigo == 200
    assert "Cotizador" in cuerpo.decode("utf-8")


def test_sirve_los_estaticos_con_su_tipo(wsgi):
    peticion = urllib.request.Request(wsgi + "/estatico/app.js")
    with urllib.request.urlopen(peticion) as r:
        assert r.status == 200
        assert "javascript" in r.headers["Content-Type"]


def test_calcula_una_cotizacion(wsgi):
    _, cuerpo = _post(wsgi, "/api/cotizacion", {
        "general": {"pax": 2},
        "opciones": [{
            "nombre": "A", "impuestos_pct": 21,
            "servicios": [{"tipo": "Hotel", "tarifa": 1000,
                           "comision_pct": 10, "gastos_admin_pct": 1.5}],
        }],
    })
    assert json.loads(cuerpo)["opciones"][0]["final"] == "1037.34"


def test_liquida_el_periodo(wsgi):
    _, cuerpo = _post(wsgi, "/api/periodo", {
        "periodo": "09/2026", "alicuota_iibb": "3.5",
        "operaciones": [{
            "mayorista": "Delfos", "comisionable": "4885", "no_comisionable": "51.13",
            "comision_pct": "3", "servicio_propio_pct": "3",
        }],
    })
    datos = json.loads(cuerpo)
    assert datos["iva"]["debito_fiscal"] == "56.53"
    assert datos["iibb"]["base"] == "269.20"


def test_lee_una_factura_subida(wsgi):
    pytest.importorskip("pymupdf", reason="PyMuPDF no esta instalado")
    pdf = RAIZ / "ejemplos" / "factura_ola_A_00012345.pdf"
    _, cuerpo = _post(wsgi, "/api/facturas", {
        "archivos": [{"nombre": pdf.name,
                      "contenido": base64.b64encode(pdf.read_bytes()).decode()}],
        "cuit_agencia": "30-71234567-9",
    })
    datos = json.loads(cuerpo)
    assert len(datos["operaciones"]) == 1
    assert datos["operaciones"][0]["comprobante_detalle"]["total"] == "712482.00"


def test_usa_el_padron_que_manda_el_navegador(wsgi):
    """Sin disco, la configuracion viaja en la peticion."""
    pytest.importorskip("pymupdf", reason="PyMuPDF no esta instalado")
    pdf = RAIZ / "ejemplos" / "factura_ola_A_00012345.pdf"
    _, cuerpo = _post(wsgi, "/api/facturas", {
        "archivos": [{"nombre": pdf.name,
                      "contenido": base64.b64encode(pdf.read_bytes()).decode()}],
        "cuit_agencia": "30-71234567-9",
        "padron": {
            "agencia": {"cuit": "30-71234567-9"},
            "mayoristas": [{"nombre": "Mi Mayorista", "comision_pct": "9.99",
                            "iva_pct": "21", "cuit": "30-58720345-1", "alias": []}],
        },
    })
    operacion = json.loads(cuerpo)["operaciones"][0]
    assert operacion["mayorista"] == "Mi Mayorista"
    assert operacion["comision_pct"] == "9.99"


# --- disco de solo lectura ---------------------------------------------------

def test_informa_que_no_puede_escribir_en_disco(wsgi):
    datos = json.loads(_get(wsgi, "/api/parametros")[1])
    assert datos["solo_lectura"] is True
    assert "hay_ocr" in datos


def test_guardar_no_escribe_pero_valida(wsgi):
    _, cuerpo = _post(wsgi, "/api/mayoristas", {
        "agencia": {"cuit": "27-12345678-9"},
        "mayoristas": [{"nombre": "Prueba", "comision_pct": "5", "iva_pct": "21"}],
    })
    datos = json.loads(cuerpo)
    assert datos["guardado_en_disco"] is False
    assert datos["mayoristas"][0]["comision_pct"] == "5.00"


def test_no_toca_el_archivo_del_repositorio(wsgi):
    antes = (RAIZ / "config" / "mayoristas.json").read_text(encoding="utf-8")
    _post(wsgi, "/api/mayoristas", {
        "agencia": {}, "mayoristas": [{"nombre": "No deberia quedar"}],
    })
    assert (RAIZ / "config" / "mayoristas.json").read_text(encoding="utf-8") == antes


# --- errores -----------------------------------------------------------------

def test_datos_invalidos_devuelven_400(wsgi):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(wsgi, "/api/cotizacion", {"opciones": [{"modalidad": "rara"}]})
    assert exc.value.code == 400


def test_ruta_inexistente(wsgi):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(wsgi, "/api/nada")
    assert exc.value.code == 404


def test_no_deja_salir_del_directorio_estatico(wsgi):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(wsgi, "/estatico/../../../etc/passwd")
    assert exc.value.code == 404


def test_metodo_no_permitido(wsgi):
    peticion = urllib.request.Request(wsgi + "/api/parametros", method="DELETE")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(peticion)
    assert exc.value.code == 405


# --- clave de acceso ---------------------------------------------------------

@pytest.fixture
def wsgi_con_clave(entorno_serverless, monkeypatch):
    monkeypatch.setenv("AGENCIA_CLAVE", "secreto123")
    servidor, base = _levantar()
    yield base
    servidor.shutdown()
    servidor.server_close()


def test_la_pagina_sigue_abierta_para_poder_pedir_la_clave(wsgi_con_clave):
    assert _get(wsgi_con_clave, "/")[0] == 200
    assert _get(wsgi_con_clave, "/estatico/app.js")[0] == 200


def test_la_api_queda_cerrada_sin_clave(wsgi_con_clave):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(wsgi_con_clave, "/api/parametros")
    assert exc.value.code == 401


def test_una_clave_equivocada_no_entra(wsgi_con_clave):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(wsgi_con_clave, "/api/parametros", {"X-Clave": "otra"})
    assert exc.value.code == 401


def test_con_la_clave_correcta_entra(wsgi_con_clave):
    assert _get(wsgi_con_clave, "/api/parametros", {"X-Clave": "secreto123"})[0] == 200


def test_sin_clave_configurada_la_api_queda_abierta(wsgi):
    assert _get(wsgi, "/api/parametros")[0] == 200

"""API del servidor web."""

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agencia.web.servidor import Manejador


@pytest.fixture(scope="module")
def servidor():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _get(base, ruta):
    with urllib.request.urlopen(f"{base}{ruta}") as r:
        return r.status, r.read().decode("utf-8")


def _post(base, ruta, datos):
    peticion = urllib.request.Request(
        f"{base}{ruta}",
        json.dumps(datos).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion) as r:
        return r.status, r.read().decode("utf-8")


# --- estaticos ---------------------------------------------------------------

def test_sirve_la_pagina(servidor):
    codigo, cuerpo = _get(servidor, "/")
    assert codigo == 200
    assert "Cotizador" in cuerpo
    assert "Liquidación" in cuerpo


def test_sirve_los_estaticos(servidor):
    assert _get(servidor, "/estatico/app.js")[0] == 200
    assert _get(servidor, "/estatico/estilos.css")[0] == 200


def test_no_deja_salir_del_directorio_estatico(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(servidor, "/estatico/../../../etc/passwd")
    assert exc.value.code == 404


def test_ruta_inexistente(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(servidor, "/api/nada")
    assert exc.value.code == 404


# --- parametros --------------------------------------------------------------

def test_parametros_para_los_formularios(servidor):
    datos = json.loads(_get(servidor, "/api/parametros")[1])
    assert len(datos["tipos_servicio"]) > 5
    assert len(datos["servicios_fiscales"]) > 10
    assert "agencia" in datos and "mayoristas" in datos


def test_lista_los_mayoristas(servidor):
    datos = json.loads(_get(servidor, "/api/mayoristas")[1])
    assert isinstance(datos["mayoristas"], list)
    assert "agencia" in datos


# --- cotizacion --------------------------------------------------------------

def _cotizacion():
    return {
        "general": {"cliente": "Test", "pax": 2, "tipo_cambio": 1450},
        "opciones": [{
            "nombre": "Opcion 1",
            "modalidad": "desglosado",
            "impuestos_pct": 21,
            "servicios": [{
                "tipo": "Hotel", "mayorista": "SIGA", "tarifa": 1000,
                "comision_pct": 10, "gastos_admin_pct": 1.5,
            }],
        }],
    }


def test_calcula_una_cotizacion(servidor):
    datos = json.loads(_post(servidor, "/api/cotizacion", _cotizacion())[1])
    opcion = datos["opciones"][0]
    assert opcion["comision"] == "100.00"
    assert opcion["gastos_admin"] == "13.50"
    assert opcion["final"] == "1037.34"


def test_devuelve_la_cotizacion_en_html(servidor):
    _, cuerpo = _post(servidor, "/api/cotizacion/html", {**_cotizacion(), "vista": "cliente"})
    assert "<!DOCTYPE html>" in cuerpo
    assert "Comision" not in cuerpo


def test_la_vista_de_agencia_muestra_la_ganancia(servidor):
    _, cuerpo = _post(servidor, "/api/cotizacion/html", {**_cotizacion(), "vista": "agencia"})
    assert "Ganancia" in cuerpo


def test_modalidad_invalida_devuelve_400(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(servidor, "/api/cotizacion", {"opciones": [{"modalidad": "rara"}]})
    assert exc.value.code == 400
    assert "desglosado" in json.loads(exc.value.read())["error"]


# --- facturas ----------------------------------------------------------------

def test_lee_una_factura_subida(servidor, raiz):
    pytest.importorskip("pymupdf", reason="PyMuPDF no esta instalado")
    pdf = raiz / "ejemplos" / "factura_ola_A_00012345.pdf"
    contenido = base64.b64encode(pdf.read_bytes()).decode()
    _, cuerpo = _post(servidor, "/api/facturas", {
        "archivos": [{"nombre": pdf.name, "contenido": contenido}],
        "cuit_agencia": "30-71234567-9",
    })
    datos = json.loads(cuerpo)
    assert len(datos["operaciones"]) == 1
    assert datos["errores"] == []
    operacion = datos["operaciones"][0]
    assert operacion["comprobante"] == "FACTURA A 0003-00012345"
    assert operacion["comprobante_detalle"]["total"] == "712482.00"


def test_un_archivo_ilegible_no_tumba_a_los_demas(servidor, raiz):
    """Cada factura se informa por separado: una mala no arruina el lote."""
    pytest.importorskip("pymupdf", reason="PyMuPDF no esta instalado")
    pdf = raiz / "ejemplos" / "factura_ola_A_00012345.pdf"
    _, cuerpo = _post(servidor, "/api/facturas", {
        "archivos": [
            {"nombre": "rota.pdf", "contenido": base64.b64encode(b"no soy un pdf").decode()},
            {"nombre": pdf.name, "contenido": base64.b64encode(pdf.read_bytes()).decode()},
        ],
        "cuit_agencia": "30-71234567-9",
    })
    datos = json.loads(cuerpo)
    assert len(datos["operaciones"]) == 1
    assert len(datos["errores"]) == 1
    assert datos["errores"][0]["archivo"] == "rota.pdf"


def test_sin_archivos_devuelve_400(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(servidor, "/api/facturas", {"archivos": []})
    assert exc.value.code == 400
    assert "ningun archivo" in json.loads(exc.value.read())["error"]


def test_archivo_corrupto_en_base64_avisa(servidor):
    _, cuerpo = _post(servidor, "/api/facturas", {
        "archivos": [{"nombre": "x.pdf", "contenido": "$$$no-es-base64$$$"}],
    })
    datos = json.loads(cuerpo)
    assert datos["errores"] and "corrupto" in datos["errores"][0]["error"]


# --- periodo -----------------------------------------------------------------

def _periodo():
    return {
        "periodo": "09/2026",
        "alicuota_iibb": "3.5",
        "jurisdiccion": "La Pampa",
        "operaciones": [{
            "fecha": "2026-09-14", "cliente": "Gomez", "mayorista": "Delfos",
            "comisionable": "4885", "no_comisionable": "51.13",
            "comision_pct": "3", "iva_pct": "21", "servicio_propio_pct": "3",
        }],
    }


def test_liquida_el_periodo(servidor):
    datos = json.loads(_post(servidor, "/api/periodo", _periodo())[1])
    assert datos["iva"]["debito_fiscal"] == "56.53"
    assert datos["iibb"]["base"] == "269.20"
    assert datos["iibb"]["determinado"] == "9.42"


def test_el_informe_del_periodo_es_html(servidor):
    _, cuerpo = _post(servidor, "/api/periodo/html", _periodo())
    assert "Liquidacion de IVA e Ingresos Brutos" in cuerpo
    assert "Ingresos Brutos a pagar" in cuerpo


def test_guarda_y_relee_el_padron(servidor, tmp_path, monkeypatch):
    original = json.loads(_get(servidor, "/api/mayoristas")[1])
    try:
        _, cuerpo = _post(servidor, "/api/mayoristas", {
            "agencia": original["agencia"],
            "mayoristas": original["mayoristas"] + [
                {"nombre": "Prueba", "comision_pct": "9.9", "iva_pct": "21", "cuit": "", "alias": []}
            ],
        })
        assert any(m["nombre"] == "Prueba" for m in json.loads(cuerpo)["mayoristas"])
    finally:
        _post(servidor, "/api/mayoristas", original)


def test_peticion_sin_datos_devuelve_400(servidor):
    peticion = urllib.request.Request(
        f"{servidor}/api/periodo", b"", {"Content-Type": "application/json"}
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(peticion)
    assert exc.value.code == 400

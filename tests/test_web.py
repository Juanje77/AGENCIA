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

def test_sirve_el_sitio_publico_en_la_raiz(servidor):
    """La raiz es lo que ve un cliente potencial: la pagina publica, no el panel."""
    codigo, cuerpo = _get(servidor, "/")
    assert codigo == 200
    assert "Esplora" in cuerpo
    assert "Cotizador" not in cuerpo


def test_sirve_el_panel_interno_aparte(servidor):
    codigo, cuerpo = _get(servidor, "/panel")
    assert codigo == 200
    assert "Cotizador" in cuerpo
    assert "Liquidación" in cuerpo


def test_cada_seccion_tiene_su_propia_pagina(servidor):
    """El sitio publico esta repartido en paginas, no todo apilado en /."""
    paginas = {
        "/servicios": "Servicios pensados para cada viaje",
        "/destinos": "Un mundo de posibilidades",
        "/salidas-grupales": "Salidas grupales",
        "/a-medida": "Viajes a medida",
        "/nosotros": "De la idea al viaje",
        "/contacto": "Planeemos tu próximo viaje",
    }
    for ruta, texto_esperado in paginas.items():
        codigo, cuerpo = _get(servidor, ruta)
        assert codigo == 200, ruta
        assert texto_esperado in cuerpo, ruta
        # Header y footer compartidos, iguales en todas las paginas.
        assert "Esplora" in cuerpo and "Acceso agencia" in cuerpo, ruta


def test_cada_salida_grupal_tiene_su_itinerario(servidor):
    """Cada flyer de "Salidas grupales" linkea a su itinerario detallado."""
    itinerarios = {
        "/salidas-grupales/bariloche": "Bariloche",
        "/salidas-grupales/iguazu": "Cataratas del Iguazú",
        "/salidas-grupales/mendoza": "Mendoza",
        "/salidas-grupales/calafate": "El Calafate",
        "/salidas-grupales/punta-cana": "Punta Cana",
        "/salidas-grupales/vina-del-mar": "Viña del Mar",
    }
    _, listado = _get(servidor, "/salidas-grupales")
    for ruta in itinerarios:
        assert f'href="{ruta}"' in listado, ruta

    for ruta, destino in itinerarios.items():
        codigo, cuerpo = _get(servidor, ruta)
        assert codigo == 200, ruta
        assert destino in cuerpo, ruta
        assert "Itinerario día por día" in cuerpo, ruta
        assert "Pagar con Mercado Pago" in cuerpo, ruta
        assert "Esplora" in cuerpo and "Acceso agencia" in cuerpo, ruta


def test_el_inicio_es_un_resumen_no_todo_apilado(servidor):
    """La home muestra una parte de cada seccion, con un link a la pagina completa."""
    _, cuerpo = _get(servidor, "/")
    assert 'href="/salidas-grupales"' in cuerpo
    assert 'href="/a-medida"' in cuerpo
    assert 'href="/servicios"' in cuerpo
    assert 'href="/destinos"' in cuerpo
    assert 'href="/nosotros"' in cuerpo
    assert 'href="/contacto"' in cuerpo
    # El formulario completo de contacto solo vive en /contacto.
    assert 'id="formulario-contacto"' not in cuerpo


def test_robots_txt_permite_el_sitio_y_bloquea_el_panel(servidor):
    codigo, cuerpo = _get(servidor, "/robots.txt")
    assert codigo == 200
    assert "Allow: /" in cuerpo
    assert "Disallow: /panel" in cuerpo
    assert "Sitemap:" in cuerpo


def test_sitemap_lista_todas_las_paginas_publicas(servidor):
    codigo, cuerpo = _get(servidor, "/sitemap.xml")
    assert codigo == 200
    for ruta in ("/", "/servicios", "/destinos", "/salidas-grupales", "/a-medida",
                 "/nosotros", "/contacto"):
        assert f"<loc>https://www.esplora.com.ar{ruta}</loc>" in cuerpo, ruta
    # El panel no es para buscadores.
    assert "/panel" not in cuerpo


def test_cada_pagina_publica_tiene_sus_tags_open_graph(servidor):
    for ruta in ("/", "/servicios", "/salidas-grupales", "/salidas-grupales/bariloche"):
        _, cuerpo = _get(servidor, ruta)
        assert 'property="og:title"' in cuerpo, ruta
        assert 'property="og:image"' in cuerpo, ruta
        assert 'name="twitter:card"' in cuerpo, ruta
        assert 'rel="canonical"' in cuerpo, ruta


def test_sirve_los_estaticos(servidor):
    assert _get(servidor, "/estatico/app.js")[0] == 200
    assert _get(servidor, "/estatico/estilos.css")[0] == 200
    assert _get(servidor, "/estatico/publico.js")[0] == 200
    assert _get(servidor, "/estatico/publico.css")[0] == 200


def test_sirve_los_logos_reales_con_su_tipo(servidor):
    """Los PNG/JPG del logo no son texto: se piden sin decodificar."""
    with urllib.request.urlopen(f"{servidor}/estatico/img/logo-icono-oscuro.png") as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "image/png"
    with urllib.request.urlopen(f"{servidor}/estatico/img/hero-esplora.jpg") as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "image/jpeg"


def test_sirve_las_variantes_webp_de_las_fotos(servidor):
    """Cada foto usada en el sitio tiene su alternativa .webp, mas liviana,
    que las paginas sirven primero via <picture>."""
    with urllib.request.urlopen(f"{servidor}/estatico/img/destinos/sol-y-mar.webp") as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "image/webp"
    with urllib.request.urlopen(f"{servidor}/estatico/img/hero-playa-480.webp") as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "image/webp"


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


# --- contacto ------------------------------------------------------------------

def _consulta():
    return {
        "nombre": "Juana Perez",
        "email": "juana@example.com",
        "telefono": "2954111111",
        "destino": "Bariloche",
        "mensaje": "Quisiera cotizar un viaje en enero.",
    }


def test_contacto_sin_smtp_configurado_avisa_para_caer_al_mailto(servidor, monkeypatch):
    """Sin SMTP_HOST, el sitio sigue funcionando: el frontend cae al mailto de siempre."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    datos = json.loads(_post(servidor, "/api/contacto", _consulta())[1])
    assert datos["enviado"] is False
    assert "SMTP_HOST" in datos["aviso"]


def test_contacto_sin_nombre_devuelve_400(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(servidor, "/api/contacto", {**_consulta(), "nombre": ""})
    assert exc.value.code == 400


def test_contacto_con_email_invalido_devuelve_400(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(servidor, "/api/contacto", {**_consulta(), "email": "no-es-un-email"})
    assert exc.value.code == 400


def test_contacto_se_manda_por_smtp_si_esta_configurado(servidor, monkeypatch):
    enviados = []

    class SMTPFalso:
        def __init__(self, host, puerto, timeout=10):
            enviados.append((host, puerto))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, usuario, clave):
            enviados.append((usuario, clave))

        def send_message(self, mensaje):
            enviados.append(mensaje)

    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setenv("SMTP_USUARIO", "bot@esplora.com.ar")
    monkeypatch.setenv("SMTP_CLAVE", "secreta")
    monkeypatch.setattr("smtplib.SMTP", SMTPFalso)

    datos = json.loads(_post(servidor, "/api/contacto", _consulta())[1])
    assert datos["enviado"] is True
    assert enviados[0] == ("smtp.ejemplo.com", 587)
    mensaje = enviados[-1]
    assert mensaje["To"] == "hola@esplora.com.ar"
    assert mensaje["Reply-To"] == "juana@example.com"


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

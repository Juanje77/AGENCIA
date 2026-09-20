"""Comandos de la linea de comandos."""

import json

import pytest

from agencia.cli import main


def test_liquidacion_imprime_el_resumen(liquidacion_ejemplo, capsys):
    codigo = main(["liquidacion", str(liquidacion_ejemplo), "--mayorista", "Ola"])
    salida = capsys.readouterr().out
    assert "Impuestos del periodo" in salida
    assert "Ingresos Brutos" in salida
    assert "Retenciones del pago" in salida
    assert codigo == 3  # hay diferencias de severidad alta


def test_liquidacion_en_json(liquidacion_ejemplo, capsys):
    main(["liquidacion", str(liquidacion_ejemplo), "--json"])
    datos = json.loads(capsys.readouterr().out)
    assert datos["liquidacion"]["lineas"] == 8
    assert "impuestos" in datos and "diferencias" in datos


def test_liquidacion_guarda_html_y_csv(liquidacion_ejemplo, tmp_path, capsys):
    html = tmp_path / "informe.html"
    csv = tmp_path / "detalle.csv"
    main(["liquidacion", str(liquidacion_ejemplo), "--html", str(html), "--csv", str(csv)])
    assert html.exists() and "<!DOCTYPE html>" in html.read_text(encoding="utf-8")
    assert csv.exists()
    assert (tmp_path / "detalle_diferencias.csv").exists()


def test_archivo_inexistente_devuelve_codigo_de_error(capsys):
    codigo = main(["liquidacion", "/tmp/no-existe-nada.csv"])
    assert codigo == 2
    assert "Error al leer el archivo" in capsys.readouterr().err


def test_cotizacion_desde_json(raiz, capsys):
    ruta = raiz / "ejemplos" / "cotizacion_bariloche.json"
    assert main(["cotizacion", str(ruta)]) == 0
    salida = capsys.readouterr().out
    assert "por pax" in salida
    assert "ganancia" in salida


def test_cotizacion_genera_las_dos_vistas(raiz, tmp_path):
    ruta = raiz / "ejemplos" / "cotizacion_bariloche.json"
    cliente, agencia = tmp_path / "c.html", tmp_path / "a.html"
    main(["cotizacion", str(ruta), "--cliente", str(cliente), "--agencia", str(agencia)])
    assert "Ganancia" not in cliente.read_text(encoding="utf-8")
    assert "Ganancia" in agencia.read_text(encoding="utf-8")


def test_factura_liquida_el_periodo(raiz, capsys):
    pytest.importorskip("pymupdf", reason="PyMuPDF no esta instalado")
    pdf = raiz / "ejemplos" / "factura_ola_A_00012345.pdf"
    assert main(["factura", str(pdf), "--periodo", "09/2026",
                 "--cuit", "30-71234567-9"]) == 0
    salida = capsys.readouterr().out
    assert "Liquidacion 09/2026" in salida
    assert "Debito fiscal" in salida
    assert "Ingresos Brutos" in salida


def test_factura_guarda_el_informe(raiz, tmp_path):
    pytest.importorskip("pymupdf", reason="PyMuPDF no esta instalado")
    pdf = raiz / "ejemplos" / "factura_ola_A_00012345.pdf"
    destino = tmp_path / "liq.html"
    main(["factura", str(pdf), "--periodo", "09/2026", "--html", str(destino)])
    assert "Liquidacion de IVA" in destino.read_text(encoding="utf-8")


def test_factura_ilegible_devuelve_error(tmp_path, capsys):
    rota = tmp_path / "rota.pdf"
    rota.write_bytes(b"no soy un pdf")
    assert main(["factura", str(rota)]) == 2
    assert "No se pudo leer" in capsys.readouterr().err


def test_mayoristas_lista_los_configurados(capsys):
    assert main(["mayoristas"]) == 0
    salida = capsys.readouterr().out
    assert "comision" in salida


def test_posicion_de_varias_liquidaciones(liquidacion_ejemplo, capsys):
    assert main(["posicion", str(liquidacion_ejemplo), "--periodo", "2026-09"]) == 0
    salida = capsys.readouterr().out
    assert "Posicion fiscal" in salida
    assert "A ingresar" in salida
    assert "Presion fiscal" in salida


def test_perfiles_lista_los_disponibles(capsys):
    assert main(["perfiles"]) == 0
    assert "plantilla" in capsys.readouterr().out


def test_parametros_muestra_la_configuracion(capsys):
    assert main(["parametros"]) == 0
    salida = capsys.readouterr().out
    assert "Ingresos Brutos" in salida
    assert "Tratamiento por servicio" in salida


def test_sin_comando_muestra_ayuda():
    with pytest.raises(SystemExit):
        main([])

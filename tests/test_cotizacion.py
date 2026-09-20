"""El cotizador por opciones."""

from decimal import Decimal as D

import pytest

from agencia.presupuestos import (
    Cotizacion,
    DatosCotizacion,
    OpcionCotizada,
    PaqueteCotizado,
    ServicioCotizado,
    calcular_cotizacion,
)
from agencia.web.informes import informe_cotizacion_agencia, informe_cotizacion_cliente
from agencia.web.mapeo import DatosInvalidos, cotizacion_desde_dict


@pytest.fixture
def desglosada():
    """Una opcion con un solo servicio, para verificar cada paso del calculo."""
    return Cotizacion(
        datos=DatosCotizacion(pax=2, tipo_cambio=D("1000")),
        opciones=[
            OpcionCotizada(
                nombre="Test",
                servicios=[
                    ServicioCotizado(
                        tipo="Hotel", tarifa=D("1000"),
                        comision_pct=D("10"), gastos_admin_pct=D("1.5"),
                    )
                ],
                impuestos_pct=D("21"),
            )
        ],
    )


def test_la_comision_sale_de_la_tarifa(desglosada):
    o = calcular_cotizacion(desglosada).opciones[0]
    assert o.comision == D("100.00")


def test_los_gastos_administrativos_se_calculan_sobre_el_neto(desglosada):
    """1,5% de (1000 - 100), no de 1000."""
    o = calcular_cotizacion(desglosada).opciones[0]
    assert o.gastos_admin == D("13.50")


def test_los_impuestos_gravan_comision_y_gastos(desglosada):
    o = calcular_cotizacion(desglosada).opciones[0]
    assert o.impuestos == D("23.84")  # 21% de 113,50


def test_la_comision_no_se_suma_al_precio(desglosada):
    """Ya viene adentro de la tarifa: sumarla seria cobrarla dos veces."""
    o = calcular_cotizacion(desglosada).opciones[0]
    assert o.final == D("1037.34")  # 1000 + 13,50 + 23,84
    assert o.por_pax == D("518.67")


def test_la_ganancia_descuenta_los_impuestos_y_no_los_gastos(desglosada):
    o = calcular_cotizacion(desglosada).opciones[0]
    assert o.ganancia == D("76.16")  # 100 - 23,84


def test_el_precio_forzado_genera_un_extra_que_es_ganancia(desglosada):
    desglosada.opciones[0].precio_por_pax_override = D("600")
    o = calcular_cotizacion(desglosada).opciones[0]
    assert o.final == D("1200.00")
    assert o.extra == D("162.66")
    assert o.ganancia == D("238.82")  # 100 - 23,84 + 162,66


def test_el_paquete_suma_impuestos_y_gastos_a_la_tarifa():
    cotizacion = Cotizacion(
        datos=DatosCotizacion(pax=2),
        opciones=[
            OpcionCotizada(
                nombre="Paquete",
                modalidad="paquete",
                paquete=PaqueteCotizado(
                    tarifa=D("2400"), comisionable_pct=D("14"),
                    gastos_admin_pct=D("1.5"), impuestos=D("100"),
                ),
            )
        ],
    )
    o = calcular_cotizacion(cotizacion).opciones[0]
    assert o.comision == D("336.00")
    assert o.gastos_admin == D("30.96")   # 1,5% de (2400 - 336)
    assert o.final == D("2530.96")
    assert o.ganancia == D("336.00")      # el paquete no descuenta impuestos


def test_identifica_la_mas_barata_y_la_mas_rentable():
    cotizacion = Cotizacion(
        datos=DatosCotizacion(pax=1),
        opciones=[
            OpcionCotizada(
                nombre="Cara y rentable",
                servicios=[ServicioCotizado(tarifa=D("2000"), comision_pct=D("20"))],
                impuestos_pct=D("0"),
            ),
            OpcionCotizada(
                nombre="Barata",
                servicios=[ServicioCotizado(tarifa=D("1000"), comision_pct=D("5"))],
                impuestos_pct=D("0"),
            ),
        ],
    )
    calculada = calcular_cotizacion(cotizacion)
    assert calculada.mas_barata.opcion.nombre == "Barata"
    assert calculada.mas_rentable.opcion.nombre == "Cara y rentable"


def test_la_carga_fiscal_real_distingue_el_tratamiento_de_cada_servicio():
    """El aereo internacional no lleva IVA sobre la comision; el hotel si."""
    cotizacion = Cotizacion(
        datos=DatosCotizacion(pax=1, tipo_cambio=D("1000")),
        opciones=[
            OpcionCotizada(
                nombre="Aereo",
                servicios=[ServicioCotizado(tipo="Aereo", tarifa=D("1000"), comision_pct=D("10"))],
            ),
            OpcionCotizada(
                nombre="Hotel",
                servicios=[ServicioCotizado(tipo="Hotel", tarifa=D("1000"), comision_pct=D("10"))],
            ),
        ],
    )
    aereo, hotel = calcular_cotizacion(cotizacion).opciones
    assert aereo.fiscal["iva_debito"] == "0.00"
    assert hotel.fiscal["iva_debito"] == "21000.00"  # 21% de 100 USD a 1000


def test_sin_tipo_de_cambio_no_calcula_la_carga_fiscal_pero_no_falla():
    cotizacion = Cotizacion(
        datos=DatosCotizacion(pax=1),
        opciones=[OpcionCotizada(servicios=[ServicioCotizado(tarifa=D("1000"))])],
    )
    calculada = calcular_cotizacion(cotizacion)
    assert calculada.opciones[0].fiscal["calculado"] is False
    assert any("cotizacion del dolar" in a for a in calculada.avisos)


def test_los_servicios_en_cero_no_entran_en_la_carga_fiscal():
    cotizacion = Cotizacion(
        datos=DatosCotizacion(pax=1, tipo_cambio=D("1000")),
        opciones=[
            OpcionCotizada(
                servicios=[
                    ServicioCotizado(tipo="Hotel", tarifa=D("1000"), comision_pct=D("10")),
                    ServicioCotizado(tipo="Hotel", tarifa=D("0")),
                ]
            )
        ],
    )
    assert len(calcular_cotizacion(cotizacion).opciones[0].fiscal["detalle"]) == 1


# --- mapeo desde JSON --------------------------------------------------------

def test_arma_la_cotizacion_desde_el_ejemplo(raiz):
    import json

    datos = json.loads(
        (raiz / "ejemplos" / "cotizacion_bariloche.json").read_text(encoding="utf-8")
    )
    calculada = calcular_cotizacion(cotizacion_desde_dict(datos))
    assert len(calculada.opciones) == 2
    assert calculada.opciones[0].final > D("0")
    assert calculada.mas_barata is not None


def test_modalidad_invalida_explica_las_opciones():
    with pytest.raises(DatosInvalidos, match="desglosado"):
        cotizacion_desde_dict({"opciones": [{"modalidad": "inventada"}]})


def test_pasajeros_no_numericos_avisa():
    with pytest.raises(DatosInvalidos, match="numero"):
        cotizacion_desde_dict({"general": {"pax": "dos"}})


def test_el_informe_del_cliente_no_muestra_comisiones(desglosada):
    html = informe_cotizacion_cliente(calcular_cotizacion(desglosada))
    assert "Comision" not in html
    assert "Ganancia" not in html
    assert "Precio por pasajero" in html


def test_el_informe_de_la_agencia_muestra_la_ganancia(desglosada):
    html = informe_cotizacion_agencia(calcular_cotizacion(desglosada))
    assert "Ganancia" in html
    assert "Comision" in html


def test_los_informes_escapan_el_contenido(desglosada):
    desglosada.datos.cliente = "<script>alert(1)</script>"
    desglosada.opciones[0].nombre_cliente = "<img onerror=x>"
    html = informe_cotizacion_cliente(calcular_cotizacion(desglosada))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html

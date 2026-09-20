"""Liquidacion de IVA e Ingresos Brutos del periodo."""

from decimal import Decimal as D

import pytest

from agencia.liquidaciones.factura import COMPRA, Comprobante
from agencia.liquidador import (
    Mayorista,
    Operacion,
    Padron,
    Periodo,
    cargar_padron,
    guardar_padron,
    operacion_desde_comprobante,
)


@pytest.fixture
def operacion():
    """El caso de la planilla: comisionable 4885, Delfos al 3%, 3% de servicio propio."""
    return Operacion(
        fecha="2026-09-14",
        cliente="Familia Gomez - Bariloche",
        mayorista="Delfos",
        comisionable=D("4885"),
        no_comisionable=D("51.13"),
        comision_pct=D("3"),
        iva_pct=D("21"),
        servicio_propio_pct=D("3"),
    )


# --- una operacion -----------------------------------------------------------

def test_la_comision_se_calcula_sobre_lo_comisionable(operacion):
    """Las tasas no gravadas no pagan comision."""
    assert operacion.comision_ganada == D("146.55")


def test_la_comision_viene_con_el_iva_adentro(operacion):
    """Para el debito fiscal hay que desagregarla: 146,55 / 1,21."""
    assert operacion.gravado == D("121.12")
    assert operacion.iva_comision == D("25.43")


def test_el_servicio_propio_se_calcula_sobre_el_total_del_viaje(operacion):
    assert operacion.total_viaje == D("4936.13")
    assert operacion.servicio_propio == D("148.08")
    assert operacion.iva_servicio == D("31.10")


def test_el_debito_suma_los_dos_ivas(operacion):
    assert operacion.debito_fiscal == D("56.53")


def test_la_base_de_iibb_es_la_comision_neta_mas_el_servicio_propio(operacion):
    assert operacion.base_iibb == D("269.20")


def test_sin_tipo_de_cambio_la_operacion_no_es_convertible():
    operacion = Operacion(moneda="USD", comisionable=D("1000"), comision_pct=D("5"))
    assert not operacion.convertible
    assert operacion.a_dict()["pesos"] is None


def test_con_tipo_de_cambio_se_expresa_en_pesos():
    operacion = Operacion(
        moneda="USD", tipo_cambio=D("1500"), comisionable=D("1000"), comision_pct=D("10")
    )
    assert operacion.convertible
    assert operacion.a_dict()["pesos"]["comision_ganada"] == "150000.00"


# --- el periodo --------------------------------------------------------------

def test_el_periodo_suma_en_pesos_y_deja_fuera_lo_no_convertible():
    periodo = Periodo(
        periodo="09/2026",
        operaciones=[
            Operacion(comisionable=D("1000"), comision_pct=D("10")),
            Operacion(moneda="USD", comisionable=D("1000"), comision_pct=D("10")),
        ],
    )
    assert periodo.debito_fiscal == D("17.36")  # solo la operacion en pesos
    assert len(periodo.operaciones_sin_convertir) == 1
    assert any("sin tipo de cambio" in a for a in periodo.avisos())


def test_el_iibb_aplica_la_alicuota_a_la_base():
    periodo = Periodo(
        alicuota_iibb=D("3.5"),
        operaciones=[Operacion(comisionable=D("121000"), comision_pct=D("100"))],
    )
    assert periodo.base_iibb == D("100000.00")
    assert periodo.iibb_determinado == D("3500.00")


def test_las_retenciones_de_iibb_se_descuentan():
    periodo = Periodo(
        alicuota_iibb=D("3.5"),
        retenciones_iibb_sufridas=D("1000"),
        operaciones=[Operacion(comisionable=D("121000"), comision_pct=D("100"))],
    )
    assert periodo.iibb_a_pagar == D("2500.00")


def test_el_credito_de_los_mayoristas_no_se_computa_por_defecto():
    """Como intermediaria, ese IVA no es de la agencia."""
    periodo = Periodo(
        operaciones=[
            Operacion(comisionable=D("121000"), comision_pct=D("100"), credito_fiscal=D("5000"))
        ]
    )
    assert periodo.credito_fiscal == D("0.00")
    assert periodo.credito_fiscal_mayoristas == D("5000.00")
    assert any("no se esta computando" in a for a in periodo.avisos())


def test_se_puede_activar_el_computo_del_credito():
    periodo = Periodo(
        computa_credito_de_mayoristas=True,
        operaciones=[
            Operacion(comisionable=D("121000"), comision_pct=D("100"), credito_fiscal=D("5000"))
        ],
    )
    assert periodo.credito_fiscal == D("5000.00")


def test_el_credito_propio_siempre_se_computa():
    periodo = Periodo(credito_fiscal_extra=D("1000"))
    assert periodo.credito_fiscal == D("1000.00")


def test_saldo_a_favor_cuando_el_credito_supera_al_debito():
    periodo = Periodo(
        credito_fiscal_extra=D("50000"),
        operaciones=[Operacion(comisionable=D("121000"), comision_pct=D("100"))],
    )
    assert periodo.iva_resultado < D("0")
    datos = periodo.a_dict()
    assert datos["iva"]["a_pagar"] == "0.00"
    assert D(datos["iva"]["saldo_a_favor"]) > D("0")
    assert any("saldo tecnico a favor" in a for a in periodo.avisos())


def test_avisa_cuando_falta_el_porcentaje_de_comision():
    periodo = Periodo(operaciones=[Operacion(comisionable=D("1000"), comision_pct=D("0"))])
    assert any("sin porcentaje de comision" in a for a in periodo.avisos())


# --- padron ------------------------------------------------------------------

def test_reconoce_al_mayorista_por_cuit():
    padron = Padron(mayoristas=[Mayorista(nombre="Ola", cuit="33-68050456-9")])
    assert padron.buscar("Cualquier cosa", "33680504569").nombre == "Ola"


def test_reconoce_al_mayorista_por_alias():
    padron = Padron(mayoristas=[Mayorista(nombre="Delfos", alias=["DELFOS OPERADOR"])])
    assert padron.buscar("DELFOS OPERADOR MAYORISTA SRL").nombre == "Delfos"


def test_mayorista_desconocido_devuelve_nada():
    assert Padron(mayoristas=[Mayorista(nombre="Ola")]).buscar("Otro") is None


def test_el_padron_se_guarda_y_se_relee(tmp_path):
    padron = Padron(mayoristas=[Mayorista(nombre="Test", comision_pct=D("7.5"))])
    padron.agencia.cuit = "27-12345678-9"
    destino = guardar_padron(padron, tmp_path / "mayoristas.json")
    releido = cargar_padron(destino)
    assert releido.mayoristas[0].comision_pct == D("7.5")
    assert releido.agencia.cuit == "27-12345678-9"


def test_padron_inexistente_no_rompe(tmp_path):
    assert cargar_padron(tmp_path / "no-existe.json").mayoristas == []


# --- desde una factura -------------------------------------------------------

def _comprobante(**cambios) -> Comprobante:
    base = dict(
        archivo="f.pdf", clase="FACTURA", letra="A", sentido=COMPRA,
        razon_social_emisor="OLA S.A.", cuit_emisor="33680504569",
        gravado_21=D("1000"), iva_21=D("210"), no_gravado=D("50"),
        total=D("1260"), fecha_emision="30/09/2026", moneda="ARS",
    )
    base.update(cambios)
    return Comprobante(**base)


def test_la_factura_llena_la_operacion():
    padron = Padron(mayoristas=[Mayorista(nombre="Ola", cuit="33-68050456-9", comision_pct=D("4.5"))])
    operacion = operacion_desde_comprobante(_comprobante(), padron)
    assert operacion.mayorista == "Ola"
    assert operacion.comision_pct == D("4.5")
    assert operacion.comisionable == D("1000.00")   # gravado + exento
    assert operacion.no_comisionable == D("50.00")  # no gravado
    assert operacion.credito_fiscal == D("210")


def test_avisa_si_el_mayorista_no_esta_configurado():
    operacion = operacion_desde_comprobante(_comprobante(), Padron())
    assert operacion.comision_pct == D("0")
    assert any("no esta en la configuracion" in a for a in operacion.avisos)


def test_avisa_si_la_lectura_del_pdf_no_cerro():
    operacion = operacion_desde_comprobante(_comprobante(confiable=False), Padron())
    assert any("no cerro contra el total" in a for a in operacion.avisos)


def test_una_nota_de_credito_no_se_confunde_con_una_factura():
    comprobante = _comprobante(clase="NOTA DE CREDITO")
    assert comprobante.signo == -1

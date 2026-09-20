"""El motor fiscal: IVA, Ingresos Brutos y retenciones."""

from decimal import Decimal as D

import pytest

from agencia.dominio import BaseIIBB, CondicionIVA, RolAgencia, TratamientoIVA
from agencia.impuestos import (
    OperacionGravada,
    calcular_operacion,
    calcular_retenciones,
    consolidar,
    iva_contenido,
    neto_desde_total,
)


# --- IVA ---------------------------------------------------------------------

def test_comision_de_aereo_internacional_no_genera_debito(params):
    """El transporte internacional esta exento y su intermediacion lo sigue."""
    op = OperacionGravada(tipo_servicio="AEREO_INTERNACIONAL", comision=D("100000"))
    r = calcular_operacion(op, params)
    assert r.debito_fiscal == D("0.00")
    assert r.desglose_iva[0].tratamiento is TratamientoIVA.EXENTO


def test_comision_de_hotel_en_el_exterior_paga_iva(params):
    """El servicio esta fuera del IVA, pero la intermediacion se presta aca."""
    op = OperacionGravada(tipo_servicio="HOTELERIA_EXTERIOR", comision=D("100000"))
    r = calcular_operacion(op, params)
    assert r.debito_fiscal == D("21000.00")


def test_el_fee_de_la_agencia_siempre_paga_21(params):
    """Aunque el servicio intermediado este exento, el fee es servicio propio."""
    op = OperacionGravada(
        tipo_servicio="AEREO_INTERNACIONAL", comision=D("100000"), fee=D("50000")
    )
    r = calcular_operacion(op, params)
    assert r.debito_fiscal == D("10500.00")  # 21% de 50000, nada sobre la comision


def test_el_over_sigue_el_tratamiento_de_la_comision(params):
    op = OperacionGravada(
        tipo_servicio="HOTELERIA_EXTERIOR", comision=D("50000"), over=D("50000")
    )
    r = calcular_operacion(op, params)
    assert r.debito_fiscal == D("21000.00")  # 21% sobre 100000


def test_organizador_tributa_sobre_el_total_y_computa_credito(params):
    """Armando el paquete propio factura todo y descuenta el IVA de compra."""
    op = OperacionGravada(
        tipo_servicio="PAQUETE_NACIONAL",
        rol=RolAgencia.ORGANIZADOR,
        costo_neto=D("1000000"),
        iva_credito_proveedor=D("210000"),
        over=D("200000"),
    )
    r = calcular_operacion(op, params)
    assert r.debito_fiscal == D("252000.00")  # 21% de 1.200.000
    assert r.credito_fiscal == D("210000.00")
    assert r.iva_a_pagar == D("42000.00")


def test_intermediario_no_computa_el_credito_del_proveedor(params):
    op = OperacionGravada(
        tipo_servicio="HOTELERIA_NACIONAL",
        costo_neto=D("1000000"),
        iva_credito_proveedor=D("210000"),
        comision=D("100000"),
    )
    r = calcular_operacion(op, params)
    assert r.credito_fiscal == D("0.00")
    assert any("no se computa el IVA" in o for o in r.observaciones)


def test_cabotaje_usa_alicuota_reducida_en_el_servicio(params):
    servicio = params.servicio("AEREO_CABOTAJE")
    assert params.alicuota_iva(servicio.iva_servicio) == D("10.50")
    assert params.alicuota_iva(servicio.iva_comision) == D("21.00")


def test_desagregar_iva_de_un_precio_final():
    assert neto_desde_total(D("121"), D("21")) == D("100.00")
    assert iva_contenido(D("121"), D("21")) == D("21.00")


# --- Ingresos Brutos ---------------------------------------------------------

def test_iibb_del_intermediario_grava_solo_la_comision(params):
    op = OperacionGravada(
        tipo_servicio="HOTELERIA_EXTERIOR", costo_neto=D("1000000"), comision=D("100000")
    )
    r = calcular_operacion(op, params)
    assert r.base_iibb_tipo is BaseIIBB.COMISION
    assert r.base_iibb == D("100000.00")
    assert r.iibb_total == D("3500.00")  # 3,5% La Pampa


def test_iibb_del_organizador_nunca_usa_base_comision(params):
    op = OperacionGravada(
        tipo_servicio="HOTELERIA_NACIONAL",
        rol=RolAgencia.ORGANIZADOR,
        costo_neto=D("1000000"),
        over=D("200000"),
    )
    r = calcular_operacion(op, params)
    assert r.base_iibb_tipo is BaseIIBB.TOTAL
    assert r.base_iibb == D("1200000.00")


def test_base_por_diferencia_en_paquetes(params):
    op = OperacionGravada(
        tipo_servicio="PAQUETE_EXTERIOR",
        costo_neto=D("1000000"),
        over=D("150000"),
        comision=D("120000"),
    )
    r = calcular_operacion(op, params)
    assert r.base_iibb_tipo is BaseIIBB.DIFERENCIA
    assert r.base_iibb == D("270000.00")  # over + comision


def test_base_negativa_se_lleva_a_cero(params):
    op = OperacionGravada(
        tipo_servicio="PAQUETE_EXTERIOR",
        costo_neto=D("1000000"),
        over=D("-200000"),
    )
    r = calcular_operacion(op, params)
    assert r.base_iibb == D("0.00")
    assert any("negativa" in o for o in r.observaciones)


def test_bajo_regimen_local_el_impuesto_va_a_la_jurisdiccion_de_la_operacion(params_locales):
    op = OperacionGravada(
        tipo_servicio="HOTELERIA_EXTERIOR", comision=D("100000"), jurisdiccion="CORDOBA"
    )
    r = calcular_operacion(op, params_locales)
    assert [d.jurisdiccion for d in r.distribucion_iibb] == ["CORDOBA"]
    assert r.iibb_total == D("4750.00")  # 4,75% de Cordoba


def test_bajo_convenio_multilateral_la_base_se_reparte_por_coeficientes(params_convenio):
    """Con Convenio la base se distribuye por el CM 05, no por operacion."""
    op = OperacionGravada(
        tipo_servicio="HOTELERIA_EXTERIOR", comision=D("100000"), jurisdiccion="CORDOBA"
    )
    r = calcular_operacion(op, params_convenio)
    reparto = {d.jurisdiccion: d.base for d in r.distribucion_iibb}
    assert reparto == {"LA_PAMPA": D("60000.00"), "CORDOBA": D("40000.00")}
    # 60.000 * 3,5% + 40.000 * 4,75%
    assert r.iibb_total == D("4000.00")


def test_coeficientes_que_no_suman_uno_generan_aviso(params_convenio_roto):
    op = OperacionGravada(tipo_servicio="HOTELERIA_EXTERIOR", comision=D("100000"))
    r = calcular_operacion(op, params_convenio_roto)
    assert any("no 1,0000" in o for o in r.observaciones)


def test_jurisdiccion_inexistente_avisa_las_validas(params):
    op = OperacionGravada(
        tipo_servicio="OTRO", comision=D("1000"), jurisdiccion="NARNIA"
    )
    with pytest.raises(KeyError, match="Jurisdiccion desconocida"):
        calcular_operacion(op, params)


def test_servicio_inexistente_avisa_los_validos(params):
    op = OperacionGravada(tipo_servicio="TELETRANSPORTE", comision=D("1000"))
    with pytest.raises(KeyError, match="Tipo de servicio desconocido"):
        calcular_operacion(op, params)


# --- Retenciones -------------------------------------------------------------

def test_ganancias_solo_retiene_sobre_el_excedente_del_minimo(params):
    """RG 830: el minimo no sujeto se resta de la base, no es un umbral."""
    minimo = params.retenciones["GANANCIAS_RG830"].minimo_no_sujeto
    base = minimo + D("100000")
    retenciones = calcular_retenciones(
        params, comision_neta=base, iva_comision=D("0"), solo_codigos=["GANANCIAS_RG830"]
    )
    assert retenciones[0].base == D("100000.00")
    assert retenciones[0].importe == D("2000.00")


def test_ganancias_no_retiene_por_debajo_del_minimo(params):
    retenciones = calcular_retenciones(
        params, comision_neta=D("10000"), iva_comision=D("0"),
        solo_codigos=["GANANCIAS_RG830"],
    )
    assert not retenciones[0].aplicada
    assert "minimo no sujeto" in retenciones[0].motivo


def test_retencion_de_iva_se_calcula_sobre_el_iva_de_la_comision(params):
    retenciones = calcular_retenciones(
        params, comision_neta=D("100000"), iva_comision=D("21000"),
        solo_codigos=["IVA_RG2854"],
    )
    assert retenciones[0].base == D("21000.00")
    assert retenciones[0].importe == D("10500.00")  # 50%


def test_no_inscripto_sufre_la_alicuota_agravada(params):
    inscripto = calcular_retenciones(
        params, comision_neta=D("500000"), iva_comision=D("0"),
        condicion=CondicionIVA.RESPONSABLE_INSCRIPTO, solo_codigos=["GANANCIAS_RG830"],
    )
    monotributo = calcular_retenciones(
        params, comision_neta=D("500000"), iva_comision=D("0"),
        condicion=CondicionIVA.MONOTRIBUTO, solo_codigos=["GANANCIAS_RG830"],
    )
    assert monotributo[0].importe > inscripto[0].importe


def test_sin_base_no_hay_retencion(params):
    retenciones = calcular_retenciones(params, comision_neta=D("0"), iva_comision=D("0"))
    assert all(not r.aplicada for r in retenciones)


# --- Consolidacion -----------------------------------------------------------

def test_consolidar_suma_por_tratamiento_y_jurisdiccion(params):
    operaciones = [
        OperacionGravada(tipo_servicio="AEREO_INTERNACIONAL", comision=D("100000")),
        OperacionGravada(tipo_servicio="HOTELERIA_EXTERIOR", comision=D("100000")),
    ]
    resultados = [calcular_operacion(o, params) for o in operaciones]
    total = consolidar(resultados)
    assert total["totales"]["operaciones"] == 2
    assert total["totales"]["debito_fiscal"] == D("21000.00")
    assert total["totales"]["retribucion_bruta"] == D("200000.00")
    assert "EXENTO" in total["por_tratamiento_iva"]
    assert "GRAVADO_21" in total["por_tratamiento_iva"]


def test_el_margen_neto_descuenta_iva_e_iibb(params):
    op = OperacionGravada(tipo_servicio="HOTELERIA_EXTERIOR", comision=D("100000"))
    r = calcular_operacion(op, params)
    assert r.carga_impositiva == D("24500.00")   # 21000 IVA + 3500 IIBB
    assert r.margen_neto == D("75500.00")
    assert r.margen_neto_pct == D("75.50")

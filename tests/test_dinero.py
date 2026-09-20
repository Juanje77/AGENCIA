"""El parseo de importes es la base: si falla, falla todo lo demas."""

from decimal import Decimal

import pytest

from agencia.dinero import (
    dec,
    dentro_de_tolerancia,
    formato_ars,
    pct,
    redondear,
    redondear_a_multiplo,
)


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("1.234,56", "1234.56"),      # formato argentino
        ("1,234.56", "1234.56"),      # formato ingles
        ("$ 1.234,56", "1234.56"),
        ("U$S 1.234,56", "1234.56"),
        ("(1.234,56)", "-1234.56"),   # negativo entre parentesis
        ("-1.234,56", "-1234.56"),
        ("1234.56", "1234.56"),
        ("1.234.567", "1234567"),     # miles con punto
        ("1234", "1234"),
        ("0,5", "0.5"),
        ("", "0.00"),
        (None, "0.00"),
        (1500, "1500"),
        (12.5, "12.5"),
    ],
)
def test_parseo_de_importes(entrada, esperado):
    assert dec(entrada) == Decimal(esperado)


def test_importe_invalido_avisa():
    with pytest.raises(ValueError, match="No se pudo interpretar"):
        dec("no es un numero")


def test_importe_invalido_con_default():
    assert dec("basura", default=Decimal("0")) == Decimal("0")


def test_redondeo_comercial_va_hacia_arriba():
    assert redondear(Decimal("1.005")) == Decimal("1.01")
    assert redondear(Decimal("2.345")) == Decimal("2.35")


def test_porcentaje():
    assert pct(Decimal("1000"), Decimal("21")) == Decimal("210.00")
    assert pct(Decimal("1000"), Decimal("10.5")) == Decimal("105.00")


def test_redondeo_a_multiplo_comercial():
    assert redondear_a_multiplo(Decimal("1234.40"), Decimal("100")) == Decimal("1200.00")
    assert redondear_a_multiplo(Decimal("1250"), Decimal("100")) == Decimal("1300.00")
    assert redondear_a_multiplo(Decimal("1234.40"), Decimal("0")) == Decimal("1234.40")


def test_formato_argentino():
    assert formato_ars(Decimal("1234567.891")) == "$ 1.234.567,89"
    assert formato_ars(Decimal("-500")) == "-$ 500,00"
    assert formato_ars(Decimal("0")) == "$ 0,00"


def test_tolerancia_absorbe_centavos():
    assert dentro_de_tolerancia(
        Decimal("1000"), Decimal("1000.50"), Decimal("1"), Decimal("0.5")
    )
    assert not dentro_de_tolerancia(
        Decimal("1000"), Decimal("1050"), Decimal("1"), Decimal("0.5")
    )

"""Manejo de importes con Decimal.

Todo el sistema trabaja con Decimal para evitar los errores de redondeo del
punto flotante: un centavo de diferencia en una liquidacion se convierte en
una diferencia de conciliacion falsa.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

CERO = Decimal("0.00")
CIEN = Decimal("100")


def dec(valor: Any, default: Decimal | None = None) -> Decimal:
    """Convierte cualquier cosa razonable a Decimal.

    Acepta los formatos que aparecen en las liquidaciones reales:
    "1.234,56" (formato argentino), "1,234.56" (formato ingles), "$ 1.234,56",
    "(1.234,56)" como negativo, "1234.56", numeros y None.
    """
    if isinstance(valor, Decimal):
        return valor
    if valor is None or valor == "":
        if default is not None:
            return default
        return CERO
    if isinstance(valor, (int,)):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))

    texto = str(valor).strip()
    if not texto:
        return default if default is not None else CERO

    negativo = False
    if texto.startswith("(") and texto.endswith(")"):
        negativo = True
        texto = texto[1:-1]

    # Cualquier simbolo de moneda o etiqueta se descarta: solo interesan los
    # digitos y los separadores. El signo se decide antes de limpiar, porque
    # puede venir detras del simbolo ("$ -500") o al final ("500-").
    if "-" in texto:
        negativo = True
    texto = re.sub(r"[^0-9.,]", "", texto)

    if not texto:
        if default is not None:
            return default
        raise ValueError(f"No se pudo interpretar el importe: {valor!r}")

    texto = _normalizar_separadores(texto)

    try:
        numero = Decimal(texto)
    except InvalidOperation:
        if default is not None:
            return default
        raise ValueError(f"No se pudo interpretar el importe: {valor!r}")

    return -numero if negativo else numero


def _normalizar_separadores(texto: str) -> str:
    """Resuelve si la coma o el punto es el separador decimal."""
    tiene_coma = "," in texto
    tiene_punto = "." in texto

    if tiene_coma and tiene_punto:
        # El ultimo separador que aparece es el decimal.
        if texto.rfind(",") > texto.rfind("."):
            return texto.replace(".", "").replace(",", ".")
        return texto.replace(",", "")
    if tiene_coma:
        # Una sola coma con 1 o 2 decimales -> separador decimal argentino.
        entero, _, resto = texto.partition(",")
        if texto.count(",") == 1 and len(resto) in (1, 2):
            return f"{entero}.{resto}"
        return texto.replace(",", "")
    if tiene_punto and texto.count(".") > 1:
        # 1.234.567 -> separador de miles.
        return texto.replace(".", "")
    return texto


def redondear(valor: Decimal, decimales: int = 2) -> Decimal:
    """Redondeo comercial (medio hacia arriba), el que usa AFIP/ARCA."""
    cuantia = Decimal(1).scaleb(-decimales)
    return dec(valor).quantize(cuantia, rounding=ROUND_HALF_UP)


def pct(base: Decimal, porcentaje: Decimal, decimales: int = 2) -> Decimal:
    """Calcula un porcentaje sobre una base."""
    return redondear(dec(base) * dec(porcentaje) / CIEN, decimales)


def redondear_a_multiplo(valor: Decimal, multiplo: Decimal) -> Decimal:
    """Redondea el precio final al multiplo comercial configurado."""
    multiplo = dec(multiplo)
    if multiplo <= CERO:
        return redondear(valor)
    unidades = (dec(valor) / multiplo).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return redondear(unidades * multiplo)


def formato_ars(valor: Decimal, simbolo: str = "$") -> str:
    """Formatea un importe al estilo argentino: $ 1.234.567,89"""
    valor = redondear(valor)
    negativo = valor < CERO
    entero, _, decimales = f"{abs(valor):.2f}".partition(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    texto = f"{simbolo} {'.'.join(grupos)},{decimales}"
    return f"-{texto}" if negativo else texto


def dentro_de_tolerancia(
    esperado: Decimal,
    informado: Decimal,
    tolerancia_absoluta: Decimal,
    tolerancia_pct: Decimal,
) -> bool:
    """Compara dos importes admitiendo la tolerancia configurada."""
    esperado, informado = dec(esperado), dec(informado)
    diferencia = abs(esperado - informado)
    if diferencia <= dec(tolerancia_absoluta):
        return True
    if esperado != CERO:
        return (diferencia / abs(esperado) * CIEN) <= dec(tolerancia_pct)
    return False

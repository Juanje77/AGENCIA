"""Importa un archivo de liquidacion y lo deja listo para conciliar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import cargar_perfil_mayorista
from ..dinero import CERO, dec
from ..dominio import Moneda
from .lectores.base import (
    ErrorDeLectura,
    detectar_formato,
    encontrar_fila_encabezado,
    leer_tabla,
)
from .modelos import Liquidacion
from .normalizador import detectar_columnas, fila_a_linea


def importar_liquidacion(
    ruta: str | Path,
    perfil: str | dict[str, Any] | None = None,
    mayorista: str = "",
    periodo: str = "",
    tipo_cambio: Any = None,
    cuit_agencia: str = "",
) -> Liquidacion:
    """Lee el archivo y devuelve la liquidacion normalizada.

    Segun el formato toma dos caminos: un PDF se lee como factura electronica
    (que es como liquidan los mayoristas), y una planilla CSV o Excel se lee
    como tabla de reservas detectando sus columnas.

    `perfil` puede ser el nombre de un archivo de config/mayoristas/ o un dict
    ya cargado. Sin perfil, las columnas se detectan automaticamente.
    """
    ruta = Path(ruta)
    nombre_perfil = "auto"

    if isinstance(perfil, str):
        nombre_perfil = perfil
        perfil = cargar_perfil_mayorista(perfil)
    elif isinstance(perfil, dict):
        nombre_perfil = perfil.get("nombre", "perfil provisto")

    perfil = perfil or {}

    if (perfil.get("formato") or detectar_formato(ruta)) == "pdf":
        from .desde_factura import importar_factura

        return importar_factura(
            ruta,
            cuit_agencia=cuit_agencia or perfil.get("cuit_agencia", ""),
            mayorista=mayorista,
            periodo=periodo,
            tipo_servicio_default=perfil.get("tipo_servicio_default", "OTRO"),
        )

    tabla = leer_tabla(ruta, perfil)
    avisos = list(tabla.avisos)

    fila_encabezado = perfil.get("fila_encabezado")
    indice = (
        int(fila_encabezado) - 1
        if fila_encabezado
        else encontrar_fila_encabezado(tabla.filas, perfil.get("columnas"))
    )
    if indice < 0 or indice >= len(tabla.filas):
        raise ErrorDeLectura(
            f"La fila de encabezado {indice + 1} esta fuera del archivo "
            f"({len(tabla.filas)} filas)."
        )
    if indice > 0:
        avisos.append(f"Encabezados detectados en la fila {indice + 1}.")

    encabezados = tabla.filas[indice]
    columnas, ignoradas = detectar_columnas(encabezados, perfil.get("columnas"))

    if "comision" not in columnas.values():
        avisos.append(
            "No se detecto una columna de comision. Sin ella no se pueden "
            "calcular el IVA ni Ingresos Brutos de la operacion."
        )

    liquidacion = Liquidacion(
        mayorista=mayorista or perfil.get("nombre", ""),
        periodo=periodo,
        archivo_origen=str(ruta),
        perfil_usado=nombre_perfil,
        tipo_cambio=dec(tipo_cambio) if tipo_cambio else CERO,
        moneda=Moneda(perfil.get("moneda_default", "ARS")),
        columnas_detectadas={str(encabezados[i]): campo for i, campo in sorted(columnas.items())},
        columnas_ignoradas=ignoradas,
        avisos=avisos,
    )

    for numero, fila in enumerate(tabla.filas[indice + 1 :], start=indice + 2):
        if _es_fila_de_totales(fila):
            continue
        linea = fila_a_linea(list(fila), columnas, numero, perfil)
        if linea is None:
            continue
        if linea.moneda is not Moneda.ARS and linea.tipo_cambio <= CERO:
            linea.tipo_cambio = liquidacion.tipo_cambio
            if linea.tipo_cambio <= CERO:
                linea.avisos.append(
                    f"Sin tipo de cambio para {linea.moneda.value}: los impuestos "
                    "no se pueden calcular en pesos."
                )
        if linea.jurisdiccion is None and perfil.get("jurisdiccion"):
            linea.jurisdiccion = perfil["jurisdiccion"]
        liquidacion.lineas.append(linea)

    if not liquidacion.lineas:
        raise ErrorDeLectura(
            f"Se leyo {ruta.name} pero no se pudo interpretar ninguna fila de datos. "
            f"Columnas detectadas: {list(liquidacion.columnas_detectadas.values()) or 'ninguna'}."
        )

    return liquidacion


PALABRAS_DE_TOTAL = ("total", "totales", "subtotal", "suma", "resumen")


def _es_fila_de_totales(fila: list[Any]) -> bool:
    """Descarta las filas de cierre para que no se cuenten dos veces."""
    from .normalizador import normalizar_texto

    celdas = [normalizar_texto(c) for c in fila if c is not None and str(c).strip()]
    if not celdas:
        return False
    texto = celdas[0]
    return any(texto == palabra or texto.startswith(palabra + " ") for palabra in PALABRAS_DE_TOTAL)

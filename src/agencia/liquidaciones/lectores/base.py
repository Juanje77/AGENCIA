"""Lectura de archivos de liquidacion a una tabla cruda de filas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_FILAS_BUSQUEDA_ENCABEZADO = 25


@dataclass
class TablaCruda:
    """Lo que devuelve cualquier lector antes de interpretar el contenido."""

    filas: list[list[Any]] = field(default_factory=list)
    origen: str = ""
    formato: str = ""
    hoja: str = ""
    avisos: list[str] = field(default_factory=list)


class ErrorDeLectura(Exception):
    """El archivo no se pudo leer o no tiene el formato esperado."""


def detectar_formato(ruta: str | Path) -> str:
    extension = Path(ruta).suffix.lower()
    if extension in (".csv", ".txt", ".tsv"):
        return "csv"
    if extension in (".xlsx", ".xlsm", ".xltx"):
        return "excel"
    if extension == ".pdf":
        return "pdf"
    if extension == ".xls":
        raise ErrorDeLectura(
            "El formato .xls (Excel 97-2003) no esta soportado. "
            "Abri el archivo y guardalo como .xlsx o .csv."
        )
    raise ErrorDeLectura(
        f"No se reconoce la extension {extension!r}. "
        "Formatos soportados: .csv, .tsv, .txt, .xlsx, .pdf"
    )


def leer_tabla(ruta: str | Path, perfil: dict[str, Any] | None = None) -> TablaCruda:
    """Despacha al lector que corresponda segun la extension del archivo."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorDeLectura(f"No existe el archivo {ruta}")

    formato = (perfil or {}).get("formato") or detectar_formato(ruta)

    if formato == "csv":
        from .csv_lector import leer_csv

        return leer_csv(ruta, perfil)
    if formato == "excel":
        from .excel_lector import leer_excel

        return leer_excel(ruta, perfil)
    if formato == "pdf":
        raise ErrorDeLectura(
            "Los PDF se leen como facturas, no como tablas. "
            "Usa agencia.liquidaciones.importar_liquidacion, que elige el camino solo."
        )
    raise ErrorDeLectura(f"Formato no soportado: {formato}")


def encontrar_fila_encabezado(
    filas: list[list[Any]], mapeo_manual: dict[str, str] | None = None
) -> int:
    """Ubica la fila de encabezados: la que reconoce mas columnas.

    Las liquidaciones suelen traer arriba el logo, el periodo y datos de la
    agencia antes de la tabla real.
    """
    from ..normalizador import detectar_columnas

    mejor_indice, mejor_puntaje = 0, -1
    limite = min(len(filas), MAX_FILAS_BUSQUEDA_ENCABEZADO)

    for indice in range(limite):
        columnas, _ = detectar_columnas(filas[indice], mapeo_manual)
        puntaje = len(columnas)
        # Desempata a favor de la fila mas alta con mas columnas reconocidas.
        if puntaje > mejor_puntaje:
            mejor_indice, mejor_puntaje = indice, puntaje

    if mejor_puntaje < 2:
        raise ErrorDeLectura(
            "No se encontro una fila de encabezados reconocible en las primeras "
            f"{limite} filas. Revisa el archivo o defini un perfil de mayorista "
            "en config/mayoristas/ con el mapeo de columnas."
        )
    return mejor_indice

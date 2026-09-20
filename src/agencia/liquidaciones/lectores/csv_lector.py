"""Lector de liquidaciones en CSV / TSV / texto delimitado."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .base import ErrorDeLectura, TablaCruda

CODIFICACIONES = ("utf-8-sig", "utf-8", "latin-1", "cp1252")
DELIMITADORES = ";,\t|"


def leer_csv(ruta: str | Path, perfil: dict[str, Any] | None = None) -> TablaCruda:
    perfil = perfil or {}
    ruta = Path(ruta)
    avisos: list[str] = []

    texto, codificacion = _leer_texto(ruta)
    if codificacion != "utf-8-sig":
        avisos.append(f"Archivo leido con codificacion {codificacion}.")

    delimitador = perfil.get("delimitador") or _detectar_delimitador(texto)

    filas = [
        list(fila)
        for fila in csv.reader(texto.splitlines(), delimiter=delimitador)
        if any(str(c).strip() for c in fila)
    ]
    if not filas:
        raise ErrorDeLectura(f"El archivo {ruta.name} no tiene filas con contenido.")

    return TablaCruda(
        filas=filas, origen=str(ruta), formato="csv", avisos=avisos
    )


def _leer_texto(ruta: Path) -> tuple[str, str]:
    for codificacion in CODIFICACIONES:
        try:
            return ruta.read_text(encoding=codificacion), codificacion
        except UnicodeDecodeError:
            continue
    raise ErrorDeLectura(
        f"No se pudo decodificar {ruta.name}. Guardalo como CSV UTF-8 y reintenta."
    )


def _detectar_delimitador(texto: str) -> str:
    muestra = "\n".join(texto.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(muestra, delimiters=DELIMITADORES).delimiter
    except csv.Error:
        # El sniffer falla con archivos de una sola columna o muy irregulares.
        conteos = {d: muestra.count(d) for d in DELIMITADORES}
        mejor = max(conteos, key=conteos.get)
        return mejor if conteos[mejor] else ","

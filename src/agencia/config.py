"""Carga de los parametros fiscales y de los perfiles de mayoristas."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from .dinero import dec
from .dominio import BaseIIBB, TratamientoIVA


def raiz_proyecto() -> Path:
    """Ubica la raiz del proyecto tanto instalado como corriendo desde el repo."""
    if (ruta := os.environ.get("AGENCIA_CONFIG_DIR")):
        return Path(ruta).expanduser().resolve().parent
    return Path(__file__).resolve().parents[2]


def dir_config() -> Path:
    if (ruta := os.environ.get("AGENCIA_CONFIG_DIR")):
        return Path(ruta).expanduser().resolve()
    return raiz_proyecto() / "config"


@dataclass(frozen=True)
class ConfigServicio:
    codigo: str
    etiqueta: str
    iva_servicio: TratamientoIVA
    iva_comision: TratamientoIVA
    iibb_base: BaseIIBB
    nota: str = ""


@dataclass(frozen=True)
class ConfigJurisdiccion:
    codigo: str
    etiqueta: str
    alicuota: Decimal
    base_default: BaseIIBB
    coeficiente_unificado: Decimal
    verificar: bool = True


@dataclass(frozen=True)
class ConfigRetencion:
    codigo: str
    etiqueta: str
    aplica_sobre: str
    alicuota_inscripto: Decimal
    alicuota_no_inscripto: Decimal
    minimo_no_sujeto: Decimal
    tipo_minimo: str
    activo: bool
    verificar: bool = True


class ParametrosFiscales:
    """Vista tipada del archivo config/parametros_fiscales.json."""

    def __init__(self, datos: dict[str, Any]):
        self.datos = datos
        self.version: str = datos.get("version", "0")
        self.aviso: str = datos.get("aviso", "")

        self.servicios: dict[str, ConfigServicio] = {
            codigo: ConfigServicio(
                codigo=codigo,
                etiqueta=cfg.get("etiqueta", codigo),
                iva_servicio=TratamientoIVA(cfg["iva_servicio"]),
                iva_comision=TratamientoIVA(cfg["iva_comision"]),
                iibb_base=BaseIIBB(cfg["iibb_base"]),
                nota=cfg.get("nota", ""),
            )
            for codigo, cfg in datos["servicios"].items()
        }

        self.jurisdicciones: dict[str, ConfigJurisdiccion] = {
            codigo: ConfigJurisdiccion(
                codigo=codigo,
                etiqueta=cfg.get("etiqueta", codigo),
                alicuota=dec(cfg["alicuota"]),
                base_default=BaseIIBB(cfg.get("base_default", "COMISION")),
                coeficiente_unificado=dec(cfg.get("coeficiente_unificado", "0")),
                verificar=bool(cfg.get("verificar", True)),
            )
            for codigo, cfg in datos["iibb"]["jurisdicciones"].items()
        }

        self.retenciones: dict[str, ConfigRetencion] = {
            codigo: ConfigRetencion(
                codigo=codigo,
                etiqueta=cfg.get("etiqueta", codigo),
                aplica_sobre=cfg["aplica_sobre"],
                alicuota_inscripto=dec(cfg["alicuota_inscripto"]),
                alicuota_no_inscripto=dec(cfg["alicuota_no_inscripto"]),
                minimo_no_sujeto=dec(cfg.get("minimo_no_sujeto", "0")),
                tipo_minimo=cfg.get("tipo_minimo", "UMBRAL"),
                activo=bool(cfg.get("activo", True)),
                verificar=bool(cfg.get("verificar", True)),
            )
            for codigo, cfg in datos["retenciones_y_percepciones"].items()
        }

        self.jurisdiccion_sede: str = datos["iibb"].get("jurisdiccion_sede", "")
        self.regimen_iibb: str = datos["iibb"].get("regimen", "LOCAL")

    # --- IVA -------------------------------------------------------------

    def alicuota_iva(self, tratamiento: TratamientoIVA) -> Decimal:
        return dec(self.datos["iva"]["tratamientos"][tratamiento.value]["alicuota"])

    def etiqueta_iva(self, tratamiento: TratamientoIVA) -> str:
        return self.datos["iva"]["tratamientos"][tratamiento.value]["etiqueta"]

    def computa_debito(self, tratamiento: TratamientoIVA) -> bool:
        return bool(
            self.datos["iva"]["tratamientos"][tratamiento.value]["computa_debito"]
        )

    # --- Accesos con error explicito -------------------------------------

    def servicio(self, codigo: str) -> ConfigServicio:
        try:
            return self.servicios[codigo]
        except KeyError:
            disponibles = ", ".join(sorted(self.servicios))
            raise KeyError(
                f"Tipo de servicio desconocido: {codigo!r}. Disponibles: {disponibles}"
            ) from None

    def jurisdiccion(self, codigo: str) -> ConfigJurisdiccion:
        try:
            return self.jurisdicciones[codigo]
        except KeyError:
            disponibles = ", ".join(sorted(self.jurisdicciones))
            raise KeyError(
                f"Jurisdiccion desconocida: {codigo!r}. Disponibles: {disponibles}"
            ) from None

    # --- Bloques sueltos --------------------------------------------------

    @property
    def presupuestos(self) -> dict[str, Any]:
        return self.datos.get("presupuestos", {})

    @property
    def percepciones_al_viajero(self) -> dict[str, Any]:
        return self.datos.get("percepciones_al_viajero", {})

    @property
    def tolerancia_absoluta(self) -> Decimal:
        return dec(self.datos["tolerancias_conciliacion"]["importe_absoluto"])

    @property
    def tolerancia_pct(self) -> Decimal:
        return dec(self.datos["tolerancias_conciliacion"]["porcentaje"])

    def advertencias_de_configuracion(self) -> list[str]:
        """Lista los parametros marcados como 'verificar' para recordarlo en los informes."""
        avisos = []
        pendientes = [j.etiqueta for j in self.jurisdicciones.values() if j.verificar]
        if pendientes:
            avisos.append(
                "Alicuotas de Ingresos Brutos pendientes de validar: "
                + ", ".join(sorted(pendientes))
            )
        pendientes = [r.etiqueta for r in self.retenciones.values() if r.verificar and r.activo]
        if pendientes:
            avisos.append(
                "Regimenes de retencion pendientes de validar: " + ", ".join(sorted(pendientes))
            )
        return avisos


@lru_cache(maxsize=8)
def cargar_parametros(ruta: str | None = None) -> ParametrosFiscales:
    """Carga (y cachea) los parametros fiscales."""
    archivo = Path(ruta) if ruta else dir_config() / "parametros_fiscales.json"
    if not archivo.exists():
        raise FileNotFoundError(
            f"No se encontro el archivo de parametros fiscales en {archivo}. "
            "Defini AGENCIA_CONFIG_DIR o copia config/parametros_fiscales.json."
        )
    with archivo.open(encoding="utf-8") as fh:
        return ParametrosFiscales(json.load(fh))


def cargar_perfil_mayorista(nombre: str) -> dict[str, Any]:
    """Carga el perfil de mapeo de columnas de un mayorista."""
    archivo = dir_config() / "mayoristas" / f"{nombre}.json"
    if not archivo.exists():
        disponibles = ", ".join(sorted(p.stem for p in perfiles_disponibles()))
        raise FileNotFoundError(
            f"No existe el perfil de mayorista {nombre!r}. Disponibles: {disponibles}"
        )
    with archivo.open(encoding="utf-8") as fh:
        return json.load(fh)


def perfiles_disponibles() -> list[Path]:
    carpeta = dir_config() / "mayoristas"
    if not carpeta.exists():
        return []
    return sorted(carpeta.glob("*.json"))

"""Cotizacion del dolar (oficial, blue, MEP y tarjeta) para el sitio y el panel.

Consulta una API publica (dolarapi.com, sin clave) y guarda el resultado en
memoria un rato (TIEMPO_DE_CACHE) para no pedirlo de nuevo en cada visita.
Si la API no responde -sin red, caida, lo que sea- se devuelve el ultimo
valor cacheado si hay uno (mejor un dato desactualizado que nada), o un
aviso claro en la respuesta en vez de romper la pagina.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

URL_API = "https://dolarapi.com/v1/dolares"
TIEMPO_DE_CACHE = 300  # 5 minutos

# dolarapi.com identifica cada cotizacion con una clave "casa". Elegimos de
# ahi las 4 que importan para un viaje: oficial (referencia), blue (la que
# mira la mayoria), bolsa (el MEP) y tarjeta (lo que termina pagando quien
# compra un paquete en dolares con tarjeta de credito).
_CASAS = {"oficial": "oficial", "blue": "blue", "bolsa": "mep", "tarjeta": "tarjeta"}

_cache: dict | None = None
_cache_momento = 0.0


def _pedir_api() -> list[dict]:
    with urllib.request.urlopen(URL_API, timeout=6) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def obtener_cotizaciones(forzar: bool = False) -> dict:
    """Devuelve oficial/blue/mep/tarjeta. Cachea TIEMPO_DE_CACHE segundos."""
    global _cache, _cache_momento

    ahora = time.time()
    if not forzar and _cache is not None and (ahora - _cache_momento) < TIEMPO_DE_CACHE:
        return _cache

    try:
        crudo = _pedir_api()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        if _cache is not None:
            return _cache
        return {"disponible": False, "aviso": f"No se pudo obtener la cotización: {exc}"}

    cotizaciones = {}
    actualizado = None
    for item in crudo:
        clave = _CASAS.get(item.get("casa"))
        if not clave:
            continue
        cotizaciones[clave] = {"compra": item.get("compra"), "venta": item.get("venta")}
        actualizado = actualizado or item.get("fechaActualizacion")

    resultado = {"disponible": True, "aviso": None, "actualizado": actualizado,
                 "cotizaciones": cotizaciones}
    _cache, _cache_momento = resultado, ahora
    return resultado

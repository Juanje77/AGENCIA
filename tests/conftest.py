import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import pytest

from agencia.config import cargar_parametros


@pytest.fixture(scope="session")
def params():
    return cargar_parametros()


@pytest.fixture(scope="session")
def raiz():
    return RAIZ


@pytest.fixture(scope="session")
def liquidacion_ejemplo(raiz):
    return raiz / "ejemplos" / "liquidacion_ola_202609.csv"


def _params_variante(**cambios):
    """Construye parametros fiscales alterando el JSON base."""
    import copy
    import json

    from agencia.config import ParametrosFiscales

    datos = copy.deepcopy(
        json.loads((RAIZ / "config" / "parametros_fiscales.json").read_text(encoding="utf-8"))
    )
    for ruta, valor in cambios.items():
        destino = datos
        partes = ruta.split(".")
        for parte in partes[:-1]:
            destino = destino[parte]
        destino[partes[-1]] = valor
    return ParametrosFiscales(datos)


@pytest.fixture(scope="session")
def params_locales():
    """Agencia que tributa en una sola jurisdiccion."""
    return _params_variante(**{"iibb.regimen": "LOCAL"})


@pytest.fixture(scope="session")
def params_convenio():
    """Agencia bajo Convenio Multilateral: 60% La Pampa, 40% Cordoba."""
    return _params_variante(
        **{
            "iibb.jurisdicciones.LA_PAMPA.coeficiente_unificado": "0.6000",
            "iibb.jurisdicciones.CORDOBA.coeficiente_unificado": "0.4000",
        }
    )


@pytest.fixture(scope="session")
def params_convenio_roto():
    """Coeficientes mal cargados, que no suman 1,0000."""
    return _params_variante(
        **{
            "iibb.jurisdicciones.LA_PAMPA.coeficiente_unificado": "0.6000",
            "iibb.jurisdicciones.CORDOBA.coeficiente_unificado": "0.1000",
        }
    )

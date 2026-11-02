"""Lo común a todos los tests: el mismo entorno se ejecuten desde donde se ejecuten."""

import os
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def pytest_configure(config):
    """Los tests usan rutas del repositorio (``bots/prudente.py``, ``docs/reglas.md``), también
    al recogerlos: se ejecutan siempre desde la raíz."""
    os.chdir(RAIZ)


@pytest.fixture(autouse=True)
def sin_variables_mus(monkeypatch):
    """La configuración por defecto, sin las variables ``MUS_*`` de quien lanza los tests
    (``MUS_PUBLICO=1`` en la terminal cambiaría lo que comprueban)."""
    for nombre in list(os.environ):
        if nombre.startswith("MUS_"):
            monkeypatch.delenv(nombre)

"""Examen automático de cada bot de la carpeta ``bots/`` (requisito 2.2).

Se ejecuta en la CI en cada Pull Request: un bot nuevo solo se fusiona si pasa todo esto.

- Se puede cargar y define **una** clase de bot, con un ``tipo`` propio que no choca con los
  bots de la librería ni con los demás de la carpeta.
- Juega partidas completas contra ``random`` y contra ``reglas`` **sin ninguna falta**: no lanza
  errores, nunca devuelve una jugada ilegal y no tarda más de 2 segundos en ninguna jugada.
- Es reproducible: con la misma semilla juega exactamente igual.
- No usa nada que no haga falta para jugar (leer la memoria del proceso, archivos, la red, el
  entorno): un primer filtro antes de la revisión de la PR (ver ``bots/README.md``).
"""

import ast
from pathlib import Path

import pytest

from musarena.arena import enfrentar
from musarena.player import Player
from musarena.players import TIPOS
from musarena.players.externos import buscar_bots, cargar_clase, crear_externo

BOTS = buscar_bots("bots")


def test_hay_al_menos_un_bot_de_ejemplo():
    assert "bots/prudente.py" in BOTS


@pytest.mark.parametrize("bot", BOTS)
def test_se_carga_y_tiene_un_tipo_propio(bot):
    clase = cargar_clase(bot)
    assert issubclass(clase, Player)
    tipo = getattr(clase, "tipo", "bot")
    assert tipo != "bot", "Pon un `tipo` propio a la clase (el nombre con el que aparece)"
    assert tipo not in TIPOS, f"El tipo {tipo!r} ya existe en la librería"
    otros = [getattr(cargar_clase(b), "tipo", "bot") for b in BOTS if b != bot]
    assert tipo not in otros, f"Otro bot de bots/ ya se llama {tipo!r}"
    assert isinstance(crear_externo(bot, seed=1), Player)


@pytest.mark.parametrize("rival", ["random", "reglas"])
@pytest.mark.parametrize("bot", BOTS)
def test_juega_partidas_completas_sin_faltas(bot, rival):
    r = enfrentar(bot, rival, partidas=6, seed=11, vigilar=True, limite_segundos=2.0)
    assert r.faltas_a == 0, f"{bot} comete faltas: {'; '.join(r.motivos_a)}"
    assert r.partidas == 6


@pytest.mark.parametrize("bot", BOTS)
def test_es_reproducible_con_la_misma_semilla(bot):
    primera = enfrentar(bot, "random", partidas=2, seed=5, vigilar=True)
    segunda = enfrentar(bot, "random", partidas=2, seed=5, vigilar=True)
    assert (primera.victorias_a, primera.vacas_a, primera.vacas_b) == \
        (segunda.victorias_a, segunda.vacas_a, segunda.vacas_b), \
        "Usa self.rng (el generador del Bot) en vez de random para que se pueda repetir"


#: Módulos que un bot no necesita para jugar y que le permitirían saltarse su Observation.
MODULOS_PROHIBIDOS = {
    "os", "sys", "inspect", "gc", "ctypes", "subprocess", "socket", "threading",
    "multiprocessing", "importlib", "pickle", "marshal", "builtins", "urllib", "http",
    "requests", "shutil", "pathlib", "io", "signal", "traceback", "weakref", "code",
}
FUNCIONES_PROHIBIDAS = {"eval", "exec", "compile", "open", "__import__", "globals", "vars",
                        "breakpoint", "setattr", "delattr"}


def usos_prohibidos(codigo: str) -> list[str]:
    """Lo que un bot no debería usar: imports peligrosos, funciones que ejecutan código o
    abren archivos, y atributos «privados» (``__dict__``, ``_current_frames``, ``f_back``…)."""
    malos = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            nombres = [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom):
            nombres = [nodo.module or ""]
        else:
            nombres = []
        malos += [f"import {n}" for n in nombres if n.split(".")[0] in MODULOS_PROHIBIDOS]
        if isinstance(nodo, ast.Name) and nodo.id in FUNCIONES_PROHIBIDAS:
            malos.append(nodo.id)
        if isinstance(nodo, ast.Attribute) and (nodo.attr.startswith("__")
                                                or nodo.attr.startswith("f_")):
            malos.append(f".{nodo.attr}")
        if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", None) == "getattr" \
                and len(nodo.args) > 1:
            nombre = nodo.args[1]
            if not isinstance(nombre, ast.Constant) or str(nombre.value).startswith("_"):
                malos.append("getattr con un nombre privado o calculado")
    return malos


@pytest.mark.parametrize("bot", BOTS)
def test_no_usa_nada_peligroso(bot):
    malos = usos_prohibidos(Path(bot).read_text(encoding="utf-8"))
    assert not malos, f"{bot} usa cosas que un bot no necesita: {', '.join(malos)}"


def test_el_filtro_detecta_los_trucos():
    trucos = """
import sys, os
from inspect import currentframe
def f(o):
    estado = sys._current_frames()
    open("/etc/passwd")
    eval("1")
    o.__dict__
    currentframe().f_back
    getattr(o, "_privado")
"""
    malos = usos_prohibidos(trucos)
    for esperado in ("import sys", "import os", "import inspect", "open", "eval", ".__dict__",
                     ".f_back", "getattr con un nombre privado o calculado"):
        assert esperado in malos, esperado
    assert usos_prohibidos("import random\nimport numpy as np\nx = getattr(o, 'tipo')\n") == []

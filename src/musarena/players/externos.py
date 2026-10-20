"""Bots externos: un bot programado en un archivo ``.py`` aparte, sin tocar la librería.

Es la forma de participar en el torneo con un bot propio. Basta con un archivo que defina una
clase que herede de :class:`~musarena.player.Player` (normalmente de
:class:`~musarena.player.Bot`)::

    # bots/mi_bot.py
    from musarena.player import Bot

    class MiBot(Bot):
        tipo = "mi_bot"

        def choose_action(self, observation, legal_actions):
            return legal_actions[0]

Se nombra con la ruta del archivo (``"bots/mi_bot.py"``) y, si el archivo tiene varias clases,
con la clase detrás (``"bots/mi_bot.py:MiBot"``). La clase se construye con ``seed=``; si no lo
acepta, sin argumentos.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
from functools import lru_cache
from pathlib import Path

from musarena.player import Bot, Player


def es_bot_externo(tipo: str) -> bool:
    """Si ``tipo`` nombra un archivo de bot (``"bots/x.py"`` o ``"bots/x.py:Clase"``)."""
    _, separador, resto = tipo.partition(".py")
    return bool(separador) and (resto == "" or resto.startswith(":"))


def _partes(tipo: str) -> tuple[Path, str | None]:
    ruta, _, clase = tipo.partition(".py")
    return Path(ruta + ".py"), (clase.lstrip(":") or None)


@lru_cache(maxsize=64)
def cargar_clase(tipo: str) -> type[Player]:
    """La clase de bot que define el archivo (se carga una sola vez por proceso)."""
    ruta, nombre = _partes(tipo)
    if not ruta.is_file():
        raise ValueError(f"No existe el archivo de bot {ruta}")
    modulo_nombre = "musarena_bot_" + hashlib.sha1(str(ruta.resolve()).encode()).hexdigest()[:10]
    spec = importlib.util.spec_from_file_location(modulo_nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    clases = [c for _, c in inspect.getmembers(modulo, inspect.isclass)
              if issubclass(c, Player) and c not in (Player, Bot) and not inspect.isabstract(c)
              and c.__module__ == modulo_nombre]
    if nombre is not None:
        clases = [c for c in clases if c.__name__ == nombre]
    if len(clases) != 1:
        encontradas = ", ".join(c.__name__ for c in clases) or "ninguna"
        raise ValueError(f"{ruta} tiene que definir una sola clase de bot (o indicarla con "
                         f"'{ruta}:Clase'); encontradas: {encontradas}")
    return clases[0]


def crear_externo(tipo: str, seed: int | None = None, nombre: str | None = None) -> Player:
    """Crea el bot del archivo ``tipo`` con su semilla (y su nombre, si la clase lo acepta)."""
    clase = cargar_clase(tipo)
    for argumentos in ({"nombre": nombre, "seed": seed}, {"seed": seed}, {}):
        try:
            return clase(**argumentos)
        except TypeError:
            continue
    return clase()


def nombre_externo(tipo: str) -> str:
    """Nombre corto para clasificaciones: el ``tipo`` de la clase o el nombre del archivo."""
    clase = cargar_clase(tipo)
    propio = getattr(clase, "tipo", "bot")
    return propio if propio != "bot" else _partes(tipo)[0].stem


def buscar_bots(carpeta: str | Path = "bots") -> list[str]:
    """Archivos de bot de una carpeta (los que empiezan por ``_`` se ignoran)."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    return [str(p.as_posix()) for p in sorted(carpeta.glob("*.py")) if not p.name.startswith("_")]

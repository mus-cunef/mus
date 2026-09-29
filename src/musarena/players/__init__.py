"""Jugadores incluidos en la librería y registro de tipos.

El registro permite crear jugadores por nombre (``crear_jugador("reglas", seed=1)``), que es lo
que usarán la línea de comandos, la arena, los torneos y la web. Para añadir un bot nuevo basta
con programar su clase y añadirla a :data:`TIPOS`.
"""

from __future__ import annotations

from typing import Any

from musarena.player import Player
from musarena.players.basic_bot import BasicBot
from musarena.players.heuristic_bot import HeuristicBot
from musarena.players.human_terminal import HumanTerminalPlayer
from musarena.players.random_bot import RandomBot

#: Tipos de jugador disponibles, por nombre.
TIPOS: dict[str, type[Player]] = {
    "humano": HumanTerminalPlayer,
    RandomBot.tipo: RandomBot,
    BasicBot.tipo: BasicBot,
    HeuristicBot.tipo: HeuristicBot,
}

#: Tipos que son bots (se pueden enfrentar en la arena sin nadie delante).
BOTS: tuple[str, ...] = tuple(nombre for nombre in TIPOS if nombre != "humano")


def crear_jugador(tipo: str, **kwargs: Any) -> Player:
    """Crea un jugador del tipo indicado; los argumentos extra se pasan al constructor."""
    try:
        clase = TIPOS[tipo]
    except KeyError:
        opciones = ", ".join(TIPOS)
        raise ValueError(f"Tipo de jugador desconocido: {tipo!r}. Opciones: {opciones}") from None
    return clase(**kwargs)


__all__ = [
    "BOTS", "TIPOS", "BasicBot", "HeuristicBot", "HumanTerminalPlayer", "RandomBot",
    "crear_jugador",
]

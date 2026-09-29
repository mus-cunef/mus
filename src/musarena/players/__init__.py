"""Jugadores incluidos en la librería y registro de tipos.

El registro permite crear jugadores por nombre (``crear_jugador("reglas", seed=1)``), que es lo
que usarán la línea de comandos, la arena, los torneos y la web. El bot ``reglas`` admite un
estilo con la forma ``"reglas:agresivo"``. Para añadir un bot nuevo basta con programar su clase
y añadirla a :data:`TIPOS`.
"""

from __future__ import annotations

from typing import Any

from musarena.player import Player
from musarena.players.basic_bot import BasicBot
from musarena.players.heuristic_bot import ESTILOS, HeuristicBot
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

#: Todas las opciones que se pueden escribir, incluidos los estilos del bot ``reglas``.
OPCIONES: tuple[str, ...] = (
    *TIPOS, *(f"{HeuristicBot.tipo}:{e}" for e in ESTILOS if e != "equilibrado")
)


def es_tipo_valido(tipo: str) -> bool:
    """Si ``tipo`` es un tipo de jugador (con estilo opcional, como ``"reglas:agresivo"``)."""
    base, _, estilo = tipo.partition(":")
    if base not in TIPOS:
        return False
    return not estilo or (base == HeuristicBot.tipo and estilo in ESTILOS)


def crear_jugador(tipo: str, **kwargs: Any) -> Player:
    """Crea un jugador del tipo indicado; los argumentos extra se pasan al constructor."""
    if not es_tipo_valido(tipo):
        opciones = ", ".join(OPCIONES)
        raise ValueError(f"Tipo de jugador desconocido: {tipo!r}. Opciones: {opciones}")
    base, _, estilo = tipo.partition(":")
    if estilo:
        kwargs.setdefault("estilo", estilo)
    return TIPOS[base](**kwargs)


__all__ = [
    "BOTS", "OPCIONES", "TIPOS", "BasicBot", "HeuristicBot", "HumanTerminalPlayer", "RandomBot",
    "crear_jugador", "es_tipo_valido",
]

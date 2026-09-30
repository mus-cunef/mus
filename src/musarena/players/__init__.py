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
from musarena.players.smart_bot import SmartBot

#: Tipos de jugador disponibles, por nombre.
TIPOS: dict[str, type[Player]] = {
    "humano": HumanTerminalPlayer,
    RandomBot.tipo: RandomBot,
    BasicBot.tipo: BasicBot,
    HeuristicBot.tipo: HeuristicBot,
    SmartBot.tipo: SmartBot,
}

#: Tipos que son bots (se pueden enfrentar en la arena sin nadie delante).
BOTS: tuple[str, ...] = tuple(nombre for nombre in TIPOS if nombre != "humano")

#: Todas las opciones que se pueden escribir, incluidos los estilos del bot ``reglas``.
OPCIONES: tuple[str, ...] = (
    *TIPOS, *(f"{HeuristicBot.tipo}:{e}" for e in ESTILOS if e != "equilibrado")
)


def es_tipo_valido(tipo: str) -> bool:
    """Si ``tipo`` es un tipo de jugador.

    Admite un estilo del bot ``reglas`` (``"reglas:agresivo"``) o un modelo del bot
    ``inteligente`` (``"inteligente:checkpoints/mejor.npz"``).
    """
    base, _, extra = tipo.partition(":")
    if base not in TIPOS:
        return False
    if not extra:
        return True
    if base == HeuristicBot.tipo:
        return extra in ESTILOS
    return base == SmartBot.tipo and extra.endswith(".npz")


def crear_jugador(tipo: str, **kwargs: Any) -> Player:
    """Crea un jugador del tipo indicado; los argumentos extra se pasan al constructor."""
    if not es_tipo_valido(tipo):
        opciones = ", ".join(OPCIONES)
        raise ValueError(f"Tipo de jugador desconocido: {tipo!r}. Opciones: {opciones} "
                         f"(o inteligente:ruta/al/modelo.npz)")
    base, _, extra = tipo.partition(":")
    if extra:
        kwargs.setdefault("estilo" if base == HeuristicBot.tipo else "modelo", extra)
    return TIPOS[base](**kwargs)


__all__ = [
    "BOTS", "OPCIONES", "TIPOS", "BasicBot", "HeuristicBot", "HumanTerminalPlayer", "RandomBot",
    "SmartBot", "crear_jugador", "es_tipo_valido",
]

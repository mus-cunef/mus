"""API de jugadores: para programar un bot basta con heredar de :class:`Player`.

Ejemplo mínimo::

    import random
    from musarena.player import Player

    class BotAleatorio(Player):
        def choose_action(self, observation, legal_actions):
            return random.choice(legal_actions)

El bot no toca el motor: recibe su :class:`~musarena.observation.Observation` y la lista de
acciones legales, y devuelve una de ellas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from musarena.actions import Action
from musarena.chat import CanalChat
from musarena.observation import Observation


class Player(ABC):
    """Un asiento de la mesa, humano o bot. El motor no distingue entre ellos."""

    def __init__(self, nombre: str | None = None) -> None:
        self.nombre = nombre or type(self).__name__
        self.asiento: int | None = None
        self.chat: CanalChat | None = None

    def sit(self, asiento: int, chat: CanalChat) -> None:
        """Lo llama :class:`~musarena.match.Match` al sentar al jugador en la mesa."""
        self.asiento = asiento
        self.chat = chat

    def say(self, texto: str) -> None:
        """Escribe en el chat abierto de la mesa (no gasta el turno)."""
        if self.chat is not None:
            self.chat.escribir(texto)

    @abstractmethod
    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        """Elige una acción de ``legal_actions`` a partir de lo que ve el jugador."""

    def on_hand_end(self, observation: Observation) -> None:  # noqa: B027
        """Aviso opcional al terminar cada mano. El resumen es ``observation.manos_jugadas[-1]``."""

    def on_game_end(self, observation: Observation) -> None:  # noqa: B027
        """Aviso opcional al terminar la partida."""

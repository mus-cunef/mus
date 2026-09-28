"""Orquesta una partida completa entre cuatro :class:`~musarena.player.Player`."""

from __future__ import annotations

import random
from collections.abc import Sequence

from musarena.actions import IllegalActionError
from musarena.chat import CanalChat, Chat
from musarena.engine import apply, legal_actions, nueva_partida
from musarena.observation import Observation, observe
from musarena.player import Player
from musarena.state import State


class Match:
    """Partida al mejor de 3 o de 5 vacas.

    El bucle es siempre el mismo: pedir la acción al jugador en turno con su observación,
    aplicarla con el motor y avisar a todos cuando termina una mano.
    """

    def __init__(
        self,
        players: Sequence[Player],
        mejor_de: int = 3,
        seed: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if len(players) != 4:
            raise ValueError("Una partida de mus necesita 4 jugadores")
        self.players = list(players)
        self.chat = Chat()
        self.state: State = nueva_partida(mejor_de=mejor_de, seed=seed, rng=rng)
        for asiento, jugador in enumerate(self.players):
            jugador.sit(asiento, CanalChat(self.chat, asiento))

    @property
    def terminada(self) -> bool:
        return self.state.terminada

    @property
    def ganador(self) -> int | None:
        """Pareja ganadora (0 = asientos 0 y 2, 1 = asientos 1 y 3), o ``None`` si no ha acabado."""
        return self.state.ganador

    def observation(self, asiento: int) -> Observation:
        return observe(self.state, asiento, self.chat.mensajes)

    def step(self) -> None:
        """Juega un turno. Si el jugador devuelve una acción ilegal se lanza
        :class:`IllegalActionError` y el estado no cambia."""
        if self.terminada:
            raise IllegalActionError("La partida ha terminado")
        asiento = self.state.turno
        manos_antes = len(self.state.manos_jugadas)
        accion = self.players[asiento].choose_action(
            self.observation(asiento), legal_actions(self.state)
        )
        self.state = apply(self.state, accion)
        self.chat.numero_mano = self.state.numero_mano
        if len(self.state.manos_jugadas) > manos_antes:
            for a, jugador in enumerate(self.players):
                jugador.on_hand_end(self.observation(a))
        if self.terminada:
            for a, jugador in enumerate(self.players):
                jugador.on_game_end(self.observation(a))

    def play(self, max_turnos: int | None = None) -> int:
        """Juega hasta el final y devuelve la pareja ganadora."""
        turnos = 0
        while not self.terminada:
            if max_turnos is not None and turnos >= max_turnos:
                raise RuntimeError(f"La partida no ha terminado en {max_turnos} turnos")
            self.step()
            turnos += 1
        return self.ganador

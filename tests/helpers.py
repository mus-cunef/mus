"""Utilidades compartidas por los tests."""

import random

from musarena.actions import Ordago
from musarena.cards import Carta, Palo
from musarena.players.random_bot import RandomBot


class JugadorAleatorio(RandomBot):
    """El bot aleatorio con dos opciones extra para los tests.

    - ``charlatan``: escribe en el chat, con su propio generador aleatorio para no cambiar sus
      jugadas; sirve para comprobar que el chat no afecta a la partida.
    - ``sin_ordago``: no echa órdagos, para que las vacas se ganen por tantos.
    """

    def __init__(self, seed: int, charlatan: bool = False, sin_ordago: bool = False) -> None:
        super().__init__(seed=seed)
        self.sin_ordago = sin_ordago
        self.rng_chat = random.Random(seed) if charlatan else None
        self.observaciones = []

    def choose_action(self, observation, legal_actions):
        self.observaciones.append(observation)
        if self.rng_chat is not None and self.rng_chat.random() < 0.3:
            self.say(f"hola desde el asiento {self.asiento}")
        if self.sin_ordago:
            sin = [a for a in legal_actions if not isinstance(a, Ordago)]
            legal_actions = sin or legal_actions
        return super().choose_action(observation, legal_actions)


_NUMEROS = {
    "A": 1, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "S": 10, "C": 11, "R": 12,
}
_PALOS = {"o": Palo.OROS, "c": Palo.COPAS, "e": Palo.ESPADAS, "b": Palo.BASTOS}


def mano(texto: str) -> list[Carta]:
    """Construye una mano desde una cadena como ``"R C S 7"``.

    Cada carta es un número/figura (A, 2-7, S, C, R) y opcionalmente un palo (o, c, e, b).
    Si no se indica palo, se reparten en orden oros, copas, espadas, bastos.
    """
    cartas = []
    palos = list(_PALOS.values())
    for i, token in enumerate(texto.split()):
        numero = _NUMEROS[token[0]]
        palo = _PALOS[token[1]] if len(token) > 1 else palos[i % 4]
        cartas.append(Carta(numero, palo))
    return cartas

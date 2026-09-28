"""Utilidades compartidas por los tests."""

from musarena.cards import Carta, Palo

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

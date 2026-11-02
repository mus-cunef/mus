"""Catálogo fijo de acciones para la red neuronal.

Una red neuronal elige entre un número fijo de salidas, así que cada acción del juego se
corresponde con una posición de este catálogo:

- ``Mus`` y ``NoHayMus``;
- los 15 descartes posibles, identificados por **qué posiciones** de la mano se tiran (la mano
  llega siempre ordenada de mayor a menor, así que la posición tiene sentido para la red);
- ``Paso``, ``Envido`` con las cantidades de :data:`CANTIDADES_ENVIDO`, ``Reenvido`` con las de
  :data:`CANTIDADES_REENVIDO` y ``Ordago``;
- ``Quiero`` y ``NoQuiero``.

En cada decisión se calcula una **máscara** con las posiciones legales; las demás se tapan, así
que la red nunca puede hacer una jugada ilegal. Las cantidades que no están en el catálogo (un
humano que envida 7) se traducen a la más cercana **que sea legal** para aprender de ellas (si
no, un ``Reenvido 13`` iría a «Reenvido 15», que puede pasar del tope y estar tapada).
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

import numpy as np

from musarena.actions import (
    Action,
    Descarte,
    Envido,
    Mus,
    NoHayMus,
    NoQuiero,
    Ordago,
    Paso,
    Quiero,
    Reenvido,
)
from musarena.cards import Carta

CANTIDADES_ENVIDO: tuple[int, ...] = (2, 3, 4, 5, 6, 8, 10, 15, 20, 30)
CANTIDADES_REENVIDO: tuple[int, ...] = (2, 3, 4, 5, 6, 8, 10, 15, 20)

#: Grupos de posiciones que se pueden descartar (de 1 a 4 cartas), en orden fijo.
DESCARTES: tuple[tuple[int, ...], ...] = tuple(
    grupo for n in range(1, 5) for grupo in combinations(range(4), n)
)

#: Nombre de cada posición del catálogo (para depurar y documentar).
NOMBRES: tuple[str, ...] = (
    "Mus",
    "No hay mus",
    *(f"Descartar posiciones {'+'.join(str(p + 1) for p in g)}" for g in DESCARTES),
    "Paso",
    *(f"Envido {n}" for n in CANTIDADES_ENVIDO),
    *(f"Reenvido {n}" for n in CANTIDADES_REENVIDO),
    "Órdago",
    "Quiero",
    "No quiero",
)
N_ACCIONES = len(NOMBRES)

MUS = 0
NO_HAY_MUS = 1
_PRIMER_DESCARTE = 2
PASO = _PRIMER_DESCARTE + len(DESCARTES)
_PRIMER_ENVIDO = PASO + 1
_PRIMER_REENVIDO = _PRIMER_ENVIDO + len(CANTIDADES_ENVIDO)
ORDAGO = _PRIMER_REENVIDO + len(CANTIDADES_REENVIDO)
QUIERO = ORDAGO + 1
NO_QUIERO = QUIERO + 1


def _mas_cercana(cantidad: int, opciones: Sequence[int], legal=None) -> int:
    """La opción más cercana a ``cantidad`` entre las que ``legal(opción)`` permite (si no hay
    ninguna, entre todas)."""
    posibles = [i for i in range(len(opciones)) if legal is None or legal(opciones[i])]
    return min(posibles or range(len(opciones)),
               key=lambda i: (abs(opciones[i] - cantidad), opciones[i]))


def indice(accion: Action, cartas: Sequence[Carta],
           legales: Sequence[Action] | None = None) -> int:
    """Posición del catálogo que corresponde a ``accion`` (con ``cartas``, la mano ordenada).

    Con ``legales``, una cantidad que no está en el catálogo va a la más cercana que sea legal
    (para entrenar con partidas humanas: la red solo aprende de posiciones legales).
    """
    permitidas = None if legales is None else set(legales)
    if isinstance(accion, Mus):
        return MUS
    if isinstance(accion, NoHayMus):
        return NO_HAY_MUS
    if isinstance(accion, Descarte):
        posiciones = tuple(i for i, c in enumerate(cartas) if c in accion.cartas)
        return _PRIMER_DESCARTE + DESCARTES.index(posiciones)
    if isinstance(accion, Paso):
        return PASO
    if isinstance(accion, Envido):
        return _PRIMER_ENVIDO + _mas_cercana(
            accion.tantos, CANTIDADES_ENVIDO,
            None if permitidas is None else lambda n: Envido(n) in permitidas)
    if isinstance(accion, Reenvido):
        return _PRIMER_REENVIDO + _mas_cercana(
            accion.tantos, CANTIDADES_REENVIDO,
            None if permitidas is None else lambda n: Reenvido(n) in permitidas)
    if isinstance(accion, Ordago):
        return ORDAGO
    if isinstance(accion, Quiero):
        return QUIERO
    if isinstance(accion, NoQuiero):
        return NO_QUIERO
    raise ValueError(f"Acción desconocida: {accion!r}")


def accion(i: int, cartas: Sequence[Carta]) -> Action:
    """Acción del juego que corresponde a la posición ``i`` del catálogo."""
    if i == MUS:
        return Mus()
    if i == NO_HAY_MUS:
        return NoHayMus()
    if _PRIMER_DESCARTE <= i < PASO:
        return Descarte(frozenset(cartas[p] for p in DESCARTES[i - _PRIMER_DESCARTE]))
    if i == PASO:
        return Paso()
    if _PRIMER_ENVIDO <= i < _PRIMER_REENVIDO:
        return Envido(CANTIDADES_ENVIDO[i - _PRIMER_ENVIDO])
    if _PRIMER_REENVIDO <= i < ORDAGO:
        return Reenvido(CANTIDADES_REENVIDO[i - _PRIMER_REENVIDO])
    if i == ORDAGO:
        return Ordago()
    if i == QUIERO:
        return Quiero()
    if i == NO_QUIERO:
        return NoQuiero()
    raise ValueError(f"Posición fuera del catálogo: {i}")


def mascara(legales: Sequence[Action], cartas: Sequence[Carta]) -> np.ndarray:
    """Vector de booleanos con las posiciones del catálogo que son jugadas legales."""
    legales = set(legales)
    m = np.zeros(N_ACCIONES, dtype=bool)
    for i in range(N_ACCIONES):
        if _PRIMER_DESCARTE <= i < PASO and len(cartas) < 4:
            continue
        m[i] = accion(i, cartas) in legales
    return m

from itertools import combinations

import pytest

from helpers import mano
from musarena.cards import todas_las_cartas
from musarena.fuerza import _manos_tipo, fuerza
from musarena.hands import Lance


def test_los_pesos_suman_todas_las_manos_de_4_cartas():
    manos = _manos_tipo()
    assert len(manos) == 330
    assert sum(peso for _, peso in manos) == 91_390  # C(40, 4)


@pytest.mark.parametrize("lance", list(Lance))
def test_fuerza_entre_0_y_1(lance):
    for texto in ["R R R R", "A A A A", "R C S A", "4 5 6 7", "R C 5 5"]:
        assert 0 <= fuerza(lance, mano(texto)) <= 1


def test_extremos():
    assert fuerza(Lance.GRANDE, mano("R R R R")) > 0.99
    assert fuerza(Lance.GRANDE, mano("A A A A")) < 0.01
    assert fuerza(Lance.CHICA, mano("A A A A")) > 0.99
    assert fuerza(Lance.PARES, mano("R R R R")) > 0.99
    assert fuerza(Lance.JUEGO, mano("R C S A")) > 0.5  # la 31 es el mejor juego...
    assert fuerza(Lance.JUEGO, mano("R R 7 6")) < 0.2  # ...y la 33 el peor


def test_orden_coherente_con_la_comparacion():
    assert fuerza(Lance.GRANDE, mano("R R 4 A")) > fuerza(Lance.GRANDE, mano("R C C C"))
    assert fuerza(Lance.PARES, mano("A A 4 4")) > fuerza(Lance.PARES, mano("R R R 5"))
    assert fuerza(Lance.PUNTO, mano("R C 5 5")) > fuerza(Lance.PUNTO, mano("R C 5 4"))


def test_coincide_con_la_enumeracion_de_todas_las_manos():
    """La tabla por rangos da lo mismo que enumerar las 91.390 manos reales."""
    from musarena.hands import clave

    mia = mano("C S 7 4")
    k = clave(Lance.GRANDE, mia)
    peores = empates = total = 0
    for rival in combinations(todas_las_cartas(), 4):
        kr = clave(Lance.GRANDE, rival)
        total += 1
        peores += kr < k
        empates += kr == k
    assert fuerza(Lance.GRANDE, mia) == pytest.approx((peores + empates / 2) / total)

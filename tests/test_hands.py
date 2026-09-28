import pytest

from helpers import mano
from musarena.cards import Carta, Palo
from musarena.hands import (
    Lance,
    TipoPares,
    bonus_juego,
    clave_chica,
    clave_grande,
    clave_juego,
    clave_pares,
    clave_punto,
    ganador,
    puntos,
    tiene_juego,
    tipo_pares,
)

# --- Valores de juego ---


@pytest.mark.parametrize(
    ("numero", "valor"),
    [(1, 1), (2, 1), (3, 10), (4, 4), (5, 5), (6, 6), (7, 7), (10, 10), (11, 10), (12, 10)],
)
def test_valor_de_juego_de_cada_carta(numero, valor):
    assert Carta(numero, Palo.OROS).valor_juego == valor


def test_puntos_y_juego():
    assert puntos(mano("R C S A")) == 31
    assert tiene_juego(mano("R C S A"))
    assert puntos(mano("R 3 7 4")) == 31
    assert puntos(mano("R R R R")) == 40
    assert puntos(mano("R C 7 2")) == 28
    assert not tiene_juego(mano("R C 7 2"))


def test_bonus_de_juego():
    assert bonus_juego(mano("R C S A")) == 3
    assert bonus_juego(mano("R C S 2")) == 3  # el 2 vale 1
    assert bonus_juego(mano("R C S R")) == 2
    assert bonus_juego(mano("R C 7 2")) == 0


# --- Grande y chica ---


def test_grande_compara_carta_a_carta():
    assert clave_grande(mano("R R 4 A")) > clave_grande(mano("R C C C"))
    assert clave_grande(mano("R C 7 A")) > clave_grande(mano("R C 6 5"))
    assert clave_grande(mano("C S 7 7")) > clave_grande(mano("S S S S"))


def test_en_grande_el_tres_es_rey_y_el_dos_es_as():
    assert clave_grande(mano("3 R 4 2")) == clave_grande(mano("R R 4 A"))


def test_chica_gana_la_mas_baja():
    assert clave_chica(mano("A A 4 R")) > clave_chica(mano("A 4 4 5"))
    assert clave_chica(mano("A 2 4 7")) > clave_chica(mano("A 2 5 6"))
    assert clave_chica(mano("2 4 5 6")) == clave_chica(mano("A 4 5 6"))


# --- Pares ---


@pytest.mark.parametrize(
    ("texto", "tipo"),
    [
        ("R C S 7", TipoPares.NADA),
        ("R 3 S 7", TipoPares.PAR),  # rey y tres forman pareja a 8 reyes
        ("A 2 S 7", TipoPares.PAR),
        ("C C C 7", TipoPares.MEDIAS),
        ("C C 7 7", TipoPares.DUPLES),
        ("R R R 3", TipoPares.DUPLES),  # cuatro reyes
    ],
)
def test_tipo_de_pares(texto, tipo):
    assert tipo_pares(mano(texto)) is tipo


def test_orden_de_pares():
    par_reyes = clave_pares(mano("R R 5 4"))
    par_sotas = clave_pares(mano("S S 5 4"))
    medias_ases = clave_pares(mano("A A A 4"))
    duples_bajos = clave_pares(mano("A A 4 4"))
    duples_reyes_caballos = clave_pares(mano("R R C C"))
    cuatro_reyes = clave_pares(mano("R R R R"))
    assert par_reyes > par_sotas
    assert medias_ases > par_reyes
    assert duples_bajos > medias_ases
    assert duples_reyes_caballos > duples_bajos
    assert cuatro_reyes > duples_reyes_caballos


# --- Juego y punto ---


def test_orden_del_juego():
    valores = [31, 32, 40, 37, 36, 35, 34, 33]
    manos = {
        31: "R C S A", 32: "R C 6 6", 40: "R R R R", 37: "R R R 7",
        36: "R R R 6", 35: "R R R 5", 34: "R R R 4", 33: "R R 7 6",
    }
    claves = []
    for v in valores:
        m = mano(manos[v])
        assert puntos(m) == v
        claves.append(clave_juego(m))
    assert claves == sorted(claves, reverse=True)
    assert len(set(claves)) == len(claves)


def test_punto_gana_el_mas_cercano_a_30():
    assert clave_punto(mano("R C 5 4")) > clave_punto(mano("R C 7 2"))  # 29 > 28
    assert clave_punto(mano("R C 5 5")) > clave_punto(mano("R C 5 4"))  # 30 > 29


# --- Empates por mano ---


def test_empate_gana_el_mas_cercano_a_la_mano():
    iguales = {s: mano("R C 7 A") for s in range(4)}
    assert ganador(Lance.GRANDE, iguales, mano=0) == 0
    assert ganador(Lance.GRANDE, iguales, mano=2) == 2
    assert ganador(Lance.CHICA, iguales, mano=3) == 3


def test_empate_parcial_por_mano():
    manos = {0: mano("R 7 5 4"), 1: mano("R C 7 A"), 2: mano("A A 4 5"), 3: mano("R C 7 A")}
    assert ganador(Lance.GRANDE, manos, mano=0) == 1
    assert ganador(Lance.GRANDE, manos, mano=3) == 3
    assert ganador(Lance.CHICA, manos, mano=1) == 2


def test_ganador_solo_entre_los_asientos_indicados():
    manos = {1: mano("S S 4 5"), 3: mano("R R 4 5")}
    assert ganador(Lance.PARES, manos, mano=0) == 3

import dataclasses

from helpers import JugadorAleatorio
from musarena.actions import Descarte, Mus, NoHayMus, Paso
from musarena.engine import apply, nueva_partida
from musarena.match import Match
from musarena.observation import Observation, observe


def _cartas_ajenas(state, asiento):
    return [c for a in range(4) if a != asiento for c in state.cartas[a]]


def _contiene_carta(obs: Observation, cartas) -> bool:
    """Busca las cartas en todos los campos de la observación (salvo las manos ya terminadas)."""
    texto = repr(dataclasses.replace(obs, manos_jugadas=()))
    return any(repr(c) in texto for c in cartas)


def test_observation_solo_tiene_mis_cartas():
    s = nueva_partida(seed=11)
    for asiento in range(4):
        obs = observe(s, asiento)
        assert obs.cartas == tuple(s.cartas[asiento])
        assert not _contiene_carta(obs, _cartas_ajenas(s, asiento))


def test_no_se_ven_las_cartas_del_companero_durante_los_lances():
    s = apply(nueva_partida(seed=12), NoHayMus())
    obs = observe(s, 0)
    assert not _contiene_carta(obs, s.cartas[2])
    assert not _contiene_carta(obs, _cartas_ajenas(s, 0))


def test_los_descartes_ajenos_no_se_ven():
    s = nueva_partida(seed=13)
    for _ in range(4):
        s = apply(s, Mus())
    tiradas = list(s.cartas[0][:2])
    s = apply(s, Descarte(frozenset(tiradas)))
    obs = observe(s, 1)
    assert not _contiene_carta(obs, tiradas)
    assert "2 cartas" in obs.historial[-1].texto


def test_cada_uno_recuerda_sus_descartes_mientras_siguen_en_la_pila():
    s = jugar_mus(nueva_partida(seed=13))
    tiradas = list(s.cartas[0][:2])
    s = apply(s, Descarte(frozenset(tiradas)))
    assert set(observe(s, 0).mis_descartes) == set(tiradas)
    assert observe(s, 1).mis_descartes == ()
    # Si se rebarajan (el mazo se acaba), vuelven al mazo y ya no se sabe dónde están.
    s.baraja.mazo = []
    s = apply(s, Descarte(frozenset(s.cartas[1][:1])))
    assert observe(s, 0).mis_descartes == ()


def jugar_mus(s):
    for _ in range(4):
        s = apply(s, Mus())
    return s


def test_la_observacion_no_expone_el_estado():
    s = nueva_partida(seed=14)
    obs = observe(s, 0)
    nombres = {f.name for f in dataclasses.fields(obs)}
    assert not nombres & {"baraja", "rng", "mazo"}
    assert not _contiene_carta(obs, s.baraja.mazo)


def test_en_ningun_momento_de_una_partida_se_filtran_cartas_ajenas():
    jugadores = [JugadorAleatorio(seed=i) for i in range(4)]
    match = Match(jugadores, seed=21)
    turnos = 0
    while not match.terminada and turnos < 400:
        for asiento in range(4):
            obs = match.observation(asiento)
            assert not _contiene_carta(obs, _cartas_ajenas(match.state, asiento))
        match.step()
        turnos += 1


def test_al_final_de_la_mano_se_ensenan_las_cuatro_manos():
    s = apply(nueva_partida(seed=15), NoHayMus())
    cartas = [tuple(c) for c in s.cartas]
    while not s.manos_jugadas:
        s = apply(s, Paso())
    assert s.manos_jugadas[0].cartas == tuple(cartas)
    assert observe(s, 1).manos_jugadas[0].cartas == tuple(cartas)

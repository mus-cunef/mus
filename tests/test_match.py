import pytest

from helpers import JugadorAleatorio
from musarena.actions import IllegalActionError, Quiero
from musarena.match import Match
from musarena.player import Player


def _partida(mejor_de, seed, charlatanes=False):
    jugadores = [JugadorAleatorio(seed=seed * 10 + i, charlatan=charlatanes) for i in range(4)]
    return Match(jugadores, mejor_de=mejor_de, seed=seed), jugadores


@pytest.mark.parametrize("seed", range(10))
def test_partida_completa_al_mejor_de_3(seed):
    match, _ = _partida(3, seed)
    ganador = match.play(max_turnos=20_000)
    assert ganador in (0, 1)
    assert match.state.vacas[ganador] == 2
    assert match.state.vacas[1 - ganador] <= 1


@pytest.mark.parametrize("seed", range(5))
def test_partida_completa_al_mejor_de_5(seed):
    match, _ = _partida(5, seed)
    ganador = match.play(max_turnos=40_000)
    assert match.state.vacas[ganador] == 3
    assert match.state.vacas[1 - ganador] <= 2


@pytest.mark.parametrize("seed", range(5))
def test_partida_completa_sin_ordagos_se_gana_por_tantos(seed):
    jugadores = [JugadorAleatorio(seed=seed * 10 + i, sin_ordago=True) for i in range(4)]
    match = Match(jugadores, mejor_de=3, seed=seed)
    ganador = match.play(max_turnos=50_000)
    vacas = [m for m in match.state.manos_jugadas if m.ganador_vaca is not None]
    assert len(vacas) == sum(match.state.vacas)
    assert all(max(m.tantos) >= 40 for m in vacas)
    assert match.state.vacas[ganador] == 2


def test_misma_semilla_misma_partida():
    a, _ = _partida(3, 7)
    b, _ = _partida(3, 7)
    a.play()
    b.play()
    assert a.state.manos_jugadas == b.state.manos_jugadas


def test_el_chat_no_altera_la_partida():
    callados, _ = _partida(3, 8)
    charlatanes, _ = _partida(3, 8, charlatanes=True)
    callados.play()
    charlatanes.play()
    assert charlatanes.chat.mensajes  # se ha escrito algo
    assert callados.state.manos_jugadas == charlatanes.state.manos_jugadas


def test_todos_leen_el_chat():
    match, jugadores = _partida(3, 9)
    jugadores[1].say("buenas")
    for asiento in range(4):
        mensajes = match.observation(asiento).chat
        assert [(m.asiento, m.texto) for m in mensajes] == [(1, "buenas")]


def test_jugadores_reciben_su_asiento_y_los_avisos():
    class Contador(JugadorAleatorio):
        manos = 0
        fin = 0

        def on_hand_end(self, observation):
            self.manos += 1

        def on_game_end(self, observation):
            self.fin += 1

    jugadores = [Contador(seed=i) for i in range(4)]
    match = Match(jugadores, seed=3)
    match.play()
    assert [j.asiento for j in jugadores] == [0, 1, 2, 3]
    assert all(j.manos == len(match.state.manos_jugadas) for j in jugadores)
    assert all(j.fin == 1 for j in jugadores)
    # cada jugador solo ha recibido observaciones de su propio asiento
    assert all(o.asiento == j.asiento for j in jugadores for o in j.observaciones)


def test_un_bot_tramposo_no_corrompe_la_partida():
    class Tramposo(Player):
        def choose_action(self, observation, legal_actions):
            return Quiero()  # casi nunca es legal en la fase de mus

    match = Match([Tramposo() for _ in range(4)], seed=1)  # hable quien hable primero
    antes = match.state
    with pytest.raises(IllegalActionError):
        match.step()
    assert match.state is antes


def test_numero_de_jugadores_y_formato():
    with pytest.raises(ValueError):
        Match([JugadorAleatorio(seed=0)] * 3)
    with pytest.raises(ValueError):
        Match([JugadorAleatorio(seed=i) for i in range(4)], mejor_de=4)

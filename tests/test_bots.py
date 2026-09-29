import pytest

from helpers import mano
from musarena.actions import (
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
from musarena.arena import enfrentar
from musarena.engine import apply, legal_actions, nueva_partida
from musarena.hands import Lance
from musarena.match import Decision, Match
from musarena.observation import observe
from musarena.player import Bot
from musarena.players import BOTS, TIPOS, HeuristicBot, RandomBot, crear_jugador


def _estado(manos, mano_inicial=0, tantos=(0, 0)):
    s = nueva_partida(seed=0, mano=mano_inicial)
    s.cartas = [mano(t) for t in manos]
    s.tantos = list(tantos)
    return s


def _decide(bot, s):
    return bot.choose_action(observe(s, s.turno), legal_actions(s))


# --- Registro ---


def test_registro_de_tipos():
    assert set(BOTS) == {"random", "reglas"}
    assert "humano" in TIPOS
    assert isinstance(crear_jugador("random", seed=1), RandomBot)
    assert isinstance(crear_jugador("reglas", seed=1), HeuristicBot)
    assert all(issubclass(TIPOS[t], Bot) for t in BOTS)
    with pytest.raises(ValueError):
        crear_jugador("experto")


# --- Partidas completas: los bots nunca hacen jugadas ilegales ---


@pytest.mark.parametrize(
    "tipos",
    [("random",) * 4, ("reglas",) * 4, ("reglas", "random", "reglas", "random"),
     ("random", "reglas", "reglas", "random")],
)
def test_partidas_completas_entre_bots(tipos):
    for seed in range(5):
        jugadores = [crear_jugador(t, seed=seed * 4 + i) for i, t in enumerate(tipos)]
        match = Match(jugadores, mejor_de=5, seed=seed)
        # Match lanza IllegalActionError si algún bot hace una jugada ilegal.
        assert match.play(max_turnos=50_000) in (0, 1)


def test_bots_reproducibles_con_semilla():
    def jugar():
        match = Match([crear_jugador("reglas", seed=i) for i in range(4)], seed=3)
        match.play()
        return match.state.manos_jugadas

    assert jugar() == jugar()


# --- Bot aleatorio ---


def test_random_elige_primero_el_tipo_de_accion():
    s = apply(nueva_partida(seed=1), NoHayMus())
    bot = RandomBot(seed=0)
    elecciones = [type(_decide(bot, s)) for _ in range(300)]
    # Paso, Envido y Órdago salen con frecuencias parecidas, aunque haya 39 envidos distintos.
    for tipo in (Paso, Envido, Ordago):
        assert 60 < elecciones.count(tipo) < 140


# --- Bot heurístico ---


def test_heuristico_corta_con_buena_mano_y_pide_mus_con_mala():
    bot = HeuristicBot(seed=0)
    assert _decide(bot, _estado(["R C S A", "4 5 6 7", "4 5 6 7", "4 5 6 7"])) == NoHayMus()
    assert _decide(bot, _estado(["R R C C", "4 5 6 7", "4 5 6 7", "4 5 6 7"])) == NoHayMus()
    assert _decide(bot, _estado(["C S 7 5", "4 5 6 7", "4 5 6 7", "4 5 6 7"])) == Mus()


def test_heuristico_descarta_a_reyes():
    bot = HeuristicBot(seed=0)
    s = _estado(["R 3 7 5", "4 5 6 7", "4 5 6 7", "4 5 6 7"])
    for _ in range(4):
        s = apply(s, Mus())
    descarte = _decide(bot, s)
    assert isinstance(descarte, Descarte)
    assert {c.numero for c in descarte.cartas} == {7, 5}


def test_heuristico_descarta_a_chica():
    bot = HeuristicBot(seed=0)
    s = _estado(["A 2 C 6", "4 5 6 7", "4 5 6 7", "4 5 6 7"])
    for _ in range(4):
        s = apply(s, Mus())
    assert {c.numero for c in _decide(bot, s).cartas} == {11, 6}


def test_heuristico_descarta_al_menos_una_carta():
    bot = HeuristicBot(seed=0)
    s = _estado(["R R 3 C", "4 5 6 7", "4 5 6 7", "4 5 6 7"])
    for _ in range(4):
        s = apply(s, Mus())
    assert _decide(bot, s) == Descarte(frozenset({s.cartas[0][3]}))  # tira el caballo


def test_heuristico_envida_con_buena_grande_y_pasa_con_mala():
    s = apply(_estado(["R R R C", "4 5 6 7", "4 5 6 7", "4 5 6 7"]), NoHayMus())
    assert isinstance(_decide(HeuristicBot(seed=0, farol=0), s), Envido)
    s = apply(_estado(["4 5 6 A", "R R R C", "4 5 6 7", "4 5 6 7"]), NoHayMus())
    assert _decide(HeuristicBot(seed=0, farol=0), s) == Paso()


def test_heuristico_rechaza_un_envite_grande_con_mala_mano():
    s = apply(_estado(["R R R C", "4 5 6 A", "4 5 6 7", "4 5 6 7"]), NoHayMus())
    s = apply(s, Envido(20))
    assert _decide(HeuristicBot(seed=0), s) == NoQuiero()


def test_heuristico_reenvida_con_mano_muy_buena():
    s = apply(_estado(["4 5 6 A", "R R R R", "4 5 6 7", "4 5 6 7"]), NoHayMus())
    s = apply(s, Envido())
    assert isinstance(_decide(HeuristicBot(seed=0), s), Reenvido)


def test_heuristico_quiere_el_ordago_si_el_rival_va_a_ganar():
    s = apply(_estado(["R R R C", "4 5 6 A", "4 5 6 7", "C 5 6 7"], tantos=(38, 0)), NoHayMus())
    s = apply(s, Ordago())
    bot = HeuristicBot(seed=0)
    # El rival tiene 38 tantos y va a ganar la vaca casi seguro, así que el bot se arriesga más:
    # aun así, con 4 5 6 A no se puede querer...
    assert _decide(bot, s) == NoQuiero()
    # ...pero con una grande decente (R C S 7) sí.
    s = apply(_estado(["R R R C", "R C S 7", "4 5 6 7", "C 5 6 7"], tantos=(38, 0)), NoHayMus())
    s = apply(s, Ordago())
    assert _decide(bot, s) == Quiero()


def test_prob_ganar_en_pares_solo_cuenta_rivales_con_pares():
    s = _estado(["R R 5 4", "S S 7 4", "4 5 6 7", "C 6 7 A"])
    s = apply(s, NoHayMus())
    for _ in range(8):  # pasan grande y chica
        s = apply(s, Paso())
    assert s.lance is Lance.PARES
    obs = observe(s, 0)
    assert obs.apuesta.participantes == (0, 1)
    p = HeuristicBot.prob_ganar(obs)
    assert 0.7 < p < 1  # pareja de reyes contra una sola pareja rival


# --- Arena y registro de decisiones ---


def test_heuristico_gana_claramente_al_aleatorio():
    resultado = enfrentar("reglas", "random", partidas=60, seed=1)
    assert resultado.porcentaje_a > 0.75


def test_arena_espejo_es_equilibrada():
    resultado = enfrentar("random", "random", partidas=100, seed=2)
    assert 0.35 < resultado.porcentaje_a < 0.65
    assert "random contra random" in str(resultado)


def test_arena_solo_admite_bots():
    with pytest.raises(ValueError):
        enfrentar("humano", "random", partidas=2)


def test_match_registra_cada_decision():
    decisiones: list[Decision] = []
    match = Match([crear_jugador("reglas", seed=i) for i in range(4)], seed=5,
                  al_decidir=decisiones.append)
    match.play()
    assert decisiones
    assert all(d.accion in d.legales for d in decisiones)
    assert all(d.observacion.asiento == d.asiento for d in decisiones)

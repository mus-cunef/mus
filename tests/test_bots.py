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
from musarena.arena import enfrentar, fabrica
from musarena.engine import apply, legal_actions, nueva_partida
from musarena.hands import Lance
from musarena.match import Decision, Match
from musarena.observation import observe
from musarena.player import Bot
from musarena.players import (
    BOTS,
    OPCIONES,
    TIPOS,
    BasicBot,
    HeuristicBot,
    RandomBot,
    crear_jugador,
    es_tipo_valido,
)
from musarena.players.heuristic_bot import ESTILOS, estilo_con

RIVALES_FLOJOS = ["4 5 6 7", "4 5 6 7", "4 5 6 7"]


def _estado(manos, mano_inicial=0, tantos=(0, 0)):
    s = nueva_partida(seed=0, mano=mano_inicial)
    s.cartas = [mano(t) for t in manos]
    s.tantos = list(tantos)
    return s


def _decide(bot, s):
    return bot.choose_action(observe(s, s.turno), legal_actions(s))


def _a_descartes(s):
    for _ in range(4):
        s = apply(s, Mus())
    return s


# --- Registro ---


def test_registro_de_tipos():
    assert set(BOTS) == {"random", "basico", "reglas", "inteligente"}
    assert "humano" in TIPOS
    assert isinstance(crear_jugador("random", seed=1), RandomBot)
    assert isinstance(crear_jugador("basico", seed=1), BasicBot)
    assert isinstance(crear_jugador("reglas", seed=1), HeuristicBot)
    assert crear_jugador("reglas", seed=1, estilo="agresivo").estilo is ESTILOS["agresivo"]
    assert crear_jugador("reglas:conservador", seed=1).estilo is ESTILOS["conservador"]
    assert all(issubclass(TIPOS[t], Bot) for t in BOTS)
    assert "reglas:agresivo" in OPCIONES
    assert es_tipo_valido("reglas:agresivo") and not es_tipo_valido("random:agresivo")
    for malo in ("experto", "reglas:loco", "random:agresivo"):
        with pytest.raises(ValueError):
            crear_jugador(malo)


# --- Partidas completas: los bots nunca hacen jugadas ilegales ---


@pytest.mark.parametrize(
    "tipos",
    [("random",) * 4, ("basico",) * 4, ("reglas",) * 4,
     ("reglas", "random", "reglas", "random"), ("basico", "reglas", "reglas", "basico")],
)
def test_partidas_completas_entre_bots(tipos):
    for seed in range(4):
        jugadores = [crear_jugador(t, seed=seed * 4 + i) for i, t in enumerate(tipos)]
        match = Match(jugadores, mejor_de=5, seed=seed)
        # Match lanza IllegalActionError si algún bot hace una jugada ilegal.
        assert match.play(max_turnos=50_000) in (0, 1)


@pytest.mark.parametrize("estilo", list(ESTILOS))
def test_cada_estilo_juega_partidas_completas(estilo):
    jugadores = [crear_jugador("reglas", seed=i, estilo=estilo) for i in range(4)]
    assert Match(jugadores, seed=1).play(max_turnos=50_000) in (0, 1)


def test_bots_reproducibles_con_semilla():
    def jugar():
        match = Match([crear_jugador("reglas", seed=i) for i in range(4)], seed=3)
        match.play()
        return match.state.manos_jugadas

    assert jugar() == jugar()


# --- Bot aleatorio ---


def test_random_elige_primero_el_tipo_de_accion():
    s = apply(nueva_partida(mano=0, seed=1), NoHayMus())
    bot = RandomBot(seed=0)
    elecciones = [type(_decide(bot, s)) for _ in range(300)]
    # Paso, Envido y Órdago salen con frecuencias parecidas, aunque haya 39 envidos distintos.
    for tipo in (Paso, Envido, Ordago):
        assert 60 < elecciones.count(tipo) < 140


# --- Bot básico (la primera versión del heurístico) ---


def test_basico_corta_con_buena_mano_y_descarta_a_reyes():
    bot = BasicBot(seed=0)
    assert _decide(bot, _estado(["R C S A", *RIVALES_FLOJOS])) == NoHayMus()
    assert _decide(bot, _estado(["C S 7 5", *RIVALES_FLOJOS])) == Mus()
    s = _a_descartes(_estado(["R 3 7 5", *RIVALES_FLOJOS]))
    assert {c.numero for c in _decide(bot, s).cartas} == {7, 5}


# --- Bot heurístico: mus y descartes ---


def test_heuristico_corta_con_buena_mano_y_pide_mus_con_mala():
    bot = HeuristicBot(seed=0)
    assert _decide(bot, _estado(["R C S A", *RIVALES_FLOJOS])) == NoHayMus()  # la 31
    assert _decide(bot, _estado(["R R 3 C", *RIVALES_FLOJOS])) == NoHayMus()
    assert _decide(bot, _estado(["4 5 6 7", *RIVALES_FLOJOS])) == Mus()
    assert "percentil" in bot.razon


def _umbral_de_corte(bot, s):
    _decide(bot, s)
    return int(bot.razon.split("umbral ")[1].rstrip("%)"))


def test_el_umbral_de_corte_depende_de_la_mesa():
    mano_ = "R 7 6 4"
    corte = ESTILOS["equilibrado"].corte
    bot = HeuristicBot(seed=0)
    # Siendo mano gana los empates: corta con 3 puntos menos.
    siendo_mano = _estado([mano_, *RIVALES_FLOJOS], mano_inicial=0)
    assert _umbral_de_corte(bot, siendo_mano) == round((corte - 0.03) * 100)
    # Tras un mus del compañero (+3: no lleva gran cosa) y otro de un rival (-2).
    tercero = _estado([mano_, *RIVALES_FLOJOS], mano_inicial=2)
    tercero = apply(apply(tercero, Mus()), Mus())  # hablan el 2 (compañero) y el 3 (rival)
    assert _umbral_de_corte(bot, tercero) == round((corte + 0.03 - 0.02) * 100)


def test_heuristico_elige_el_mejor_descarte():
    bot = HeuristicBot(seed=0)
    s = _a_descartes(_estado(["R 3 7 5", *RIVALES_FLOJOS]))
    assert {c.numero for c in _decide(bot, s).cartas} == {7, 5}  # se queda los reyes
    s = _a_descartes(_estado(["R R 3 C", *RIVALES_FLOJOS]))
    assert _decide(bot, s) == Descarte(frozenset({s.cartas[0][3]}))  # tira solo el caballo
    s = _a_descartes(_estado(["4 5 6 7", *RIVALES_FLOJOS]))
    assert len(_decide(bot, s).cartas) == 4


# --- Bot heurístico: apuestas ---


def test_heuristico_envida_con_buena_mano_y_pasa_con_mala():
    sin_faroles = estilo_con(farol=0, pasar_para_querer=0)
    s = apply(_estado(["R R C S", *RIVALES_FLOJOS]), NoHayMus())
    assert isinstance(_decide(HeuristicBot(seed=0, estilo=sin_faroles), s), (Envido, Ordago))
    s = apply(_estado(["4 5 6 A", "R R R C", "4 5 6 7", "4 5 6 7"]), NoHayMus())
    assert _decide(HeuristicBot(seed=0, estilo=sin_faroles), s) == Paso()


def test_heuristico_rechaza_un_envite_grande_con_mala_mano():
    s = apply(_estado(["R R R C", "4 5 6 A", "4 5 6 7", "C 5 6 7"]), NoHayMus())
    s = apply(s, Envido(10))
    bot = HeuristicBot(seed=0)
    assert _decide(bot, s) == NoQuiero()
    assert "sin querer" in bot.razon


def test_heuristico_quiere_si_no_querer_le_hace_perder_la_vaca():
    """Con el rival a 39, un "no quiero" le da el tanto 40: hay que querer con cualquier mano."""
    manos = ["R R R C", "4 5 6 A", "4 5 6 7", "C 5 6 7"]
    s = apply(_estado(manos, tantos=(39, 0)), NoHayMus())
    s = apply(apply(s, Envido()), NoQuiero())  # el 1 no quiere; decide el 3
    assert s.turno == 3
    assert _decide(HeuristicBot(seed=0), s) == Quiero()


def test_heuristico_sube_con_mano_muy_buena():
    s = apply(_estado(["4 5 6 A", "R R R R", "4 5 6 7", "4 5 6 7"]), NoHayMus())
    s = apply(s, Envido())
    assert isinstance(_decide(HeuristicBot(seed=0), s), (Reenvido, Ordago))


def test_heuristico_echa_ordago_antes_si_la_vaca_va_mal():
    estilo = ESTILOS["equilibrado"]
    assert estilo.umbral_ordago(0.05) < estilo.umbral_ordago(0.5) < estilo.umbral_ordago(0.9)
    # Mano buena pero no de órdago con la vaca igualada...
    manos = ["R C 7 4", "4 5 6 A", "5 6 7 A", "4 5 6 A"]
    s = apply(_estado(manos), NoHayMus())
    sin_azar = estilo_con(farol=0, pasar_para_querer=0)
    assert _decide(HeuristicBot(seed=0, estilo=sin_azar), s) != Ordago()
    # ...que sí lo es si los rivales están a punto de ganar la vaca.
    s = apply(_estado(manos, tantos=(0, 37)), NoHayMus())
    assert _decide(HeuristicBot(seed=0, estilo=sin_azar), s) == Ordago()


def test_heuristico_explica_cada_jugada():
    bot = HeuristicBot(seed=2)
    razones = []

    def al_decidir(d):
        if d.asiento == 0:
            razones.append(bot.razon)

    Match([bot, *[crear_jugador("reglas", seed=i) for i in range(3)]], seed=2,
          al_decidir=al_decidir).play()
    assert razones and all(razones)


def test_heuristico_aprende_de_los_rivales():
    bot = HeuristicBot(seed=0)
    for k in range(4):  # varias partidas: el aleatorio acaba cada una en pocas manos
        Match([bot, *[crear_jugador("random", seed=10 * k + i) for i in range(3)]], seed=k).play()
    modelos = bot.modelos_rivales(0)
    # El aleatorio envida y quiere sin mano muchísimo más que lo que supone el modelo general.
    assert modelos[1].farol > bot.modelo.farol and modelos[3].farol > bot.modelo.farol


def test_prob_en_pares_solo_cuenta_rivales_con_pares():
    s = apply(_estado(["R R 5 4", "S S 7 4", "4 5 6 7", "C 6 7 A"]), NoHayMus())
    for _ in range(8):  # pasan grande y chica
        s = apply(s, Paso())
    assert s.lance is Lance.PARES and s.apuesta.participantes == (0, 1)
    bot = HeuristicBot(seed=0, estilo=estilo_con(farol=0, pasar_para_querer=0))
    accion = _decide(bot, s)
    p = int(bot.razon.split("con ")[1].split("%")[0]) / 100
    assert p > 0.7  # pareja de reyes contra una sola pareja rival más baja
    assert isinstance(accion, (Envido, Ordago))


# --- Arena y registro de decisiones ---


def test_la_escalera_de_bots():
    """Cada bot gana claramente al anterior."""
    assert enfrentar("basico", "random", partidas=60, seed=1).porcentaje_a > 0.75
    assert enfrentar("reglas", "random", partidas=60, seed=1).porcentaje_a > 0.75
    assert enfrentar("reglas", "basico", partidas=200, seed=1).porcentaje_a > 0.6


def test_arena_espejo_es_equilibrada():
    resultado = enfrentar("random", "random", partidas=100, seed=2)
    assert 0.35 < resultado.porcentaje_a < 0.65
    assert "random contra random" in str(resultado)


def test_arena_con_estilos_y_fabricas():
    assert fabrica("reglas:conservador")(1).estilo is ESTILOS["conservador"]
    r = enfrentar(lambda seed: HeuristicBot(seed=seed), "random", partidas=4)
    assert r.partidas == 4 and r.tipo_a == "<lambda>"
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


def test_el_resumen_de_la_mano_guarda_sus_acciones():
    match = Match([crear_jugador("reglas", seed=i) for i in range(4)], seed=6)
    match.play()
    for resumen in match.state.manos_jugadas:
        assert resumen.historial and resumen.historial[0].texto.startswith("Mano")

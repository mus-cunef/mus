import pytest

from helpers import JugadorAleatorio
from musarena.actions import Descarte, Envido, Mus, NoHayMus, Ordago, Paso, Quiero, Reenvido
from musarena.cli import crear_mesa, main, preguntar_jugadores, preguntar_mejor_de
from musarena.engine import apply, legal_actions, nueva_partida
from musarena.match import Match
from musarena.observation import observe
from musarena.players import HeuristicBot, HumanTerminalPlayer, RandomBot, crear_jugador


def _humano(respuestas, **kwargs):
    entradas = iter(respuestas)
    salida: list[str] = []
    jugador = HumanTerminalPlayer(
        entrada=lambda _: next(entradas), salida=salida.append, **kwargs
    )
    return jugador, salida


def _elegir(estado, respuestas, asiento=None):
    jugador, salida = _humano(respuestas)
    asiento = estado.turno if asiento is None else asiento
    accion = jugador.choose_action(observe(estado, asiento), legal_actions(estado))
    return accion, salida


def test_muestra_las_cartas_con_su_nombre():
    s = nueva_partida(seed=1)
    _, salida = _elegir(s, ["1"])
    texto = "\n".join(salida)
    for carta in s.cartas[0]:
        assert str(carta) in texto
    for carta in s.cartas[2]:  # las del compañero no
        assert str(carta) not in texto


def test_elegir_por_numero():
    s = nueva_partida(seed=1)
    assert _elegir(s, ["1"])[0] == Mus()
    assert _elegir(s, ["2"])[0] == NoHayMus()


def test_entrada_no_valida_vuelve_a_preguntar():
    s = nueva_partida(seed=1)
    accion, salida = _elegir(s, ["", "hola", "0", "-1", "9", "2"])
    assert accion == NoHayMus()
    assert sum("Escribe un número" in linea for linea in salida) == 5


def _en_grande():
    return apply(nueva_partida(seed=1), NoHayMus())


def test_menu_de_apuestas():
    s = _en_grande()
    assert _elegir(s, ["1"])[0] == Paso()
    assert _elegir(s, ["2"])[0] == Envido(2)
    assert _elegir(s, ["3", "2", "41", "15"])[0] == Envido(15)
    assert _elegir(s, ["4"])[0] == Ordago()


def test_menu_de_respuesta():
    s = apply(_en_grande(), Envido())
    assert _elegir(s, ["1"])[0] == Quiero()
    assert _elegir(s, ["3", "1", "2"])[0] == Reenvido(2)


def test_reenvido_limitado_por_el_total_de_40():
    s = apply(_en_grande(), Envido(35))
    accion, salida = _elegir(s, ["3", "6", "5"])
    assert accion == Reenvido(5)
    assert any("Reenvido N (2-5)" in linea for linea in salida)
    assert any("entre 2 y 5" in linea for linea in salida)


def test_descarte_por_numeros():
    s = nueva_partida(seed=1)
    for _ in range(4):
        s = apply(s, Mus())
    accion, _ = _elegir(s, ["", "5", "1 3"])
    assert accion == Descarte(frozenset({s.cartas[0][0], s.cartas[0][2]}))


def test_chat_desde_la_terminal():
    humano, salida = _humano(["/chat ¡vaya cartas!", "1"])
    otros = [JugadorAleatorio(seed=i) for i in range(3)]
    match = Match([humano, *otros], seed=2)
    match.step()
    assert [(m.asiento, m.texto) for m in match.chat.mensajes] == [(0, "¡vaya cartas!")]
    assert "(mensaje enviado al chat)" in salida


def test_aviso_de_turno_con_pausa():
    s = nueva_partida(seed=1)
    preguntas: list[str] = []
    respuestas = iter(["", "1"])

    def entrada(pregunta):
        preguntas.append(pregunta)
        return next(respuestas)

    jugador = HumanTerminalPlayer(entrada=entrada, salida=lambda _: None, pausa_entre_turnos=True)
    assert jugador.choose_action(observe(s, 0), legal_actions(s)) == Mus()
    assert "Turno de Jugador 1" in preguntas[0]  # el asiento 0 se muestra como Jugador 1


def test_partida_entera_de_un_humano_contra_aleatorios():
    import itertools

    respuestas = itertools.cycle(["2", "1"])  # corta el mus; luego primera opción
    humano = HumanTerminalPlayer(entrada=lambda _: next(respuestas), salida=lambda _: None)
    match = Match([humano, *[JugadorAleatorio(seed=i) for i in range(3)]], seed=4)
    assert match.play(max_turnos=50_000) in (0, 1)


class _HumanoVigilado(HumanTerminalPlayer):
    """Humano que siempre elige la primera opción y comprueba lo que se le enseña.

    - En cada turno: no puede aparecer ninguna carta que tengan ahora los otros tres.
    - Al terminar cada mano: deben aparecer las cartas de los cuatro.
    """

    def __init__(self):
        self.lineas: list[str] = []
        self.turnos = self.manos = 0
        self.match = None
        super().__init__(entrada=self._responder, salida=self.lineas.append)

    def _responder(self, pregunta):
        return "1 2" if "descartas" in pregunta else "1"

    def choose_action(self, observation, legal_actions):
        antes = len(self.lineas)
        accion = super().choose_action(observation, legal_actions)
        pantalla = "\n".join(self.lineas[antes:])
        estado = self.match.state  # la acción aún no se ha aplicado: son las cartas actuales
        for asiento in (1, 2, 3):
            for carta in estado.cartas[asiento]:
                assert str(carta) not in pantalla, f"Se ve la carta {carta} del asiento {asiento}"
        for carta in estado.cartas[0]:
            assert str(carta) in pantalla  # las propias sí
        self.turnos += 1
        return accion

    def on_hand_end(self, observation):
        antes = len(self.lineas)
        super().on_hand_end(observation)
        resumen = "\n".join(self.lineas[antes:])
        for cartas in observation.manos_jugadas[-1].cartas:
            for carta in cartas:
                assert str(carta) in resumen
        self.manos += 1


@pytest.mark.parametrize("seed", range(4))
def test_contra_bots_solo_se_ven_sus_acciones_y_las_cartas_al_final(seed):
    humano = _HumanoVigilado()
    bots = [crear_jugador(tipo, seed=seed * 3 + i)
            for i, tipo in enumerate(["reglas", "random", "reglas"])]
    match = Match([humano, *bots], seed=seed)
    humano.match = match
    match.play(max_turnos=50_000)
    assert humano.turnos > 0 and humano.manos == len(match.state.manos_jugadas)
    # Las acciones de los bots sí se ven (por ejemplo, sus "Mus" / "No hay mus").
    pantalla = "\n".join(humano.lineas)
    assert any(f"Jugador {n}:" in pantalla for n in (2, 3, 4))


def test_preguntar_jugadores(capsys):
    respuestas = iter(["", "reglas", "robot", "RANDOM", "humano"])
    assert preguntar_jugadores(lambda _: next(respuestas)) == ["humano", "reglas", "random",
                                                               "humano"]


def test_crear_mesa_mixta():
    mesa = crear_mesa(["reglas", "humano", "random", "humano"], seed=1)
    assert isinstance(mesa[0], HeuristicBot) and isinstance(mesa[2], RandomBot)
    assert mesa[1].pausa_entre_turnos and mesa[3].pausa_entre_turnos  # dos humanos
    assert mesa[1].mostrar_resumenes and not mesa[3].mostrar_resumenes


def test_un_humano_contra_bots_no_hace_pausa():
    mesa = crear_mesa(["humano", "reglas", "reglas", "reglas"])
    assert not mesa[0].pausa_entre_turnos and mesa[0].mostrar_resumenes


def test_mus_play_solo_bots(capsys):
    assert main(["--jugadores", "reglas,random,reglas,random", "--mejor-de", "3",
                 "--seed", "1"]) == 0
    salida = capsys.readouterr().out
    assert "Fin de la mano 1" in salida
    assert "Resultado: pareja" in salida


def test_mus_play_rechaza_jugadores_mal_escritos():
    import pytest

    with pytest.raises(SystemExit):
        main(["--jugadores", "humano,reglas"])


def test_preguntar_mejor_de():
    respuestas = iter(["4", "cinco", "5"])
    assert preguntar_mejor_de(lambda _: next(respuestas)) == 5

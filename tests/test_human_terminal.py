from helpers import JugadorAleatorio
from musarena.actions import Descarte, Envido, Mus, NoHayMus, Ordago, Paso, Quiero, Reenvido
from musarena.cli import preguntar_mejor_de
from musarena.engine import apply, legal_actions, nueva_partida
from musarena.match import Match
from musarena.observation import observe
from musarena.players import HumanTerminalPlayer


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


def test_preguntar_mejor_de():
    respuestas = iter(["4", "cinco", "5"])
    assert preguntar_mejor_de(lambda _: next(respuestas)) == 5

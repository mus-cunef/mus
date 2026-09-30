import pytest

from helpers import mano
from musarena.actions import (
    Descarte,
    Envido,
    IllegalActionError,
    Mus,
    NoHayMus,
    NoQuiero,
    Ordago,
    Paso,
    Quiero,
    Reenvido,
)
from musarena.cards import ordenar_cartas
from musarena.engine import apply, legal_actions, nueva_partida, vacas_para_ganar
from musarena.hands import Lance
from musarena.state import Fase, TipoResultado

# Manos de referencia (mano = asiento 0):
#  - grande: gana el 0 (R R C 7)          - chica: gana el 1 (A A 4 5)
#  - pares: tienen el 0 (reyes) y el 1 (ases); el 2 y el 3 no
#  - juego: solo el 0 (37); la pareja B no tiene juego -> sin apuesta, A cobra 2
MANOS = ["R R C 7", "A A 4 5", "S 6 5 4", "C 7 6 4"]


def preparar(manos=MANOS, mano_inicial=0, tantos=(0, 0), vacas=(0, 0), mejor_de=3):
    """Estado recién cortado el mus, con las manos indicadas."""
    s = nueva_partida(mejor_de=mejor_de, seed=0, mano=mano_inicial)
    s.cartas = [mano(t) for t in manos]
    s.tantos = list(tantos)
    s.vacas = list(vacas)
    return apply(s, NoHayMus())


def jugar(s, *acciones):
    for a in acciones:
        s = apply(s, a)
    return s


def pasan(n):
    return [Paso()] * n


def huella(s):
    return (
        s.fase, s.turno, s.lance, [list(c) for c in s.cartas], list(s.tantos), list(s.vacas),
        len(s.historial), s.rng.getstate(), list(s.baraja.mazo), s.numero_mano,
    )


# --- Partida y mus ---


def test_vacas_para_ganar():
    assert vacas_para_ganar(3) == 2
    assert vacas_para_ganar(5) == 3
    with pytest.raises(ValueError):
        vacas_para_ganar(4)


def test_reparto_inicial():
    s = nueva_partida(seed=1)
    assert s.fase is Fase.MUS and s.turno == 0
    todas = [c for cartas in s.cartas for c in cartas]
    assert all(len(c) == 4 for c in s.cartas)
    assert len(set(todas)) == 16
    assert len(s.baraja.mazo) == 24


def test_las_manos_se_reparten_y_se_reponen_ordenadas():
    s = nueva_partida(seed=9)
    assert all(c == ordenar_cartas(c) for c in s.cartas)
    s = jugar(s, Mus(), Mus(), Mus(), Mus())
    for _ in range(4):
        s = apply(s, Descarte(frozenset(s.cartas[s.turno][:2])))
        assert all(c == ordenar_cartas(c) for c in s.cartas)


def test_misma_semilla_mismo_reparto():
    assert nueva_partida(seed=5).cartas == nueva_partida(seed=5).cartas
    assert nueva_partida(seed=5).cartas != nueva_partida(seed=6).cartas


def test_todos_mus_lleva_a_descartes_y_vuelve_al_mus():
    s = jugar(nueva_partida(seed=3), Mus(), Mus(), Mus())
    assert s.fase is Fase.MUS and s.turno == 3
    s = apply(s, Mus())
    assert s.fase is Fase.DESCARTE and s.turno == 0
    antes = list(s.cartas[0])
    s = apply(s, Descarte(frozenset(antes[:2])))
    assert len(s.cartas[0]) == 4
    assert antes[2] in s.cartas[0] and antes[3] in s.cartas[0]
    assert antes[0] not in s.cartas[0] and antes[1] not in s.cartas[0]
    for _ in range(3):
        s = apply(s, legal_actions(s)[0])
    assert s.fase is Fase.MUS and s.turno == 0
    todas = [c for cartas in s.cartas for c in cartas]
    assert len(set(todas)) == 16


def test_los_descartes_solo_se_barajan_cuando_se_acaba_el_mazo():
    """Varias rondas de mus tirando las cuatro cartas: el mazo (24) se acaba en la segunda.

    Los descartes no vuelven al mazo hasta que se acaba; entonces se barajan solo los
    descartes (nunca las cartas en mano).
    """
    s = nueva_partida(seed=4)
    for ronda in range(4):
        s = jugar(s, Mus(), Mus(), Mus(), Mus())
        for _ in range(4):
            asiento = s.turno
            tiradas = set(s.cartas[asiento])
            mazo_antes = len(s.baraja.mazo)
            descartes_antes = list(s.baraja.descartes)
            s = apply(s, Descarte(frozenset(tiradas)))
            if mazo_antes >= 4:  # hay mazo: los descartes se acumulan aparte
                assert not tiradas & set(s.cartas[asiento])
                assert len(s.baraja.mazo) == mazo_antes - 4
                assert s.baraja.descartes[:len(descartes_antes)] == descartes_antes
                assert set(s.baraja.descartes[len(descartes_antes):]) == tiradas
            en_mano = [c for cartas in s.cartas for c in cartas]
            todas = en_mano + s.baraja.mazo + s.baraja.descartes
            assert len(todas) == len(set(todas)) == 40  # ninguna carta se pierde ni se repite
            assert not set(en_mano) & set(s.baraja.mazo + s.baraja.descartes)
        if ronda == 0:
            assert len(s.baraja.mazo) == 8 and len(s.baraja.descartes) == 16


def test_si_el_mazo_se_acaba_a_mitad_se_barajan_todos_los_descartes():
    """Se descarta de 3 y queda 1 carta: la roba, se barajan todos los descartes (incluidos
    los suyos de ahora) y roba las 2 que le faltan."""
    le_vuelve_alguna = False
    for seed in range(20):
        s = jugar(nueva_partida(seed=seed), Mus(), Mus(), Mus(), Mus())
        resto = list(s.baraja.mazo)
        s.baraja.mazo, s.baraja.descartes = resto[:1], resto[1:3]  # 1 en el mazo, 2 tiradas
        ultima_del_mazo, antiguas = resto[0], set(resto[1:3])
        guardada, *tiradas = s.cartas[0]
        s = apply(s, Descarte(frozenset(tiradas)))
        nuevas = set(s.cartas[0]) - {guardada}
        assert ultima_del_mazo in nuevas
        assert nuevas - {ultima_del_mazo} <= antiguas | set(tiradas)
        assert len(s.baraja.mazo) == 3 and s.baraja.descartes == []
        le_vuelve_alguna |= bool(nuevas & set(tiradas))
    assert le_vuelve_alguna  # sus propias cartas también entran en el barajado


def test_descartes_legales_son_de_1_a_4_cartas_propias():
    s = jugar(nueva_partida(seed=3), Mus(), Mus(), Mus(), Mus())
    legales = legal_actions(s)
    assert len(legales) == 15  # subconjuntos no vacíos de 4 cartas
    assert all(a.cartas <= set(s.cartas[0]) for a in legales)


def test_cortar_mus_empieza_la_grande():
    s = apply(nueva_partida(seed=3), NoHayMus())
    assert s.fase is Fase.LANCE and s.lance is Lance.GRANDE and s.turno == 0


# --- Apuestas ---


def test_acciones_sin_envite_previo():
    s = preparar()
    legales = legal_actions(s)
    assert Paso() in legales and Envido() in legales and Ordago() in legales
    assert Envido(3) in legales and Envido(40) in legales
    assert Envido(41) not in legales and Quiero() not in legales


def test_acciones_ante_un_envite():
    s = jugar(preparar(), Envido())
    assert s.turno == 1
    legales = legal_actions(s)
    assert Quiero() in legales and NoQuiero() in legales and Ordago() in legales
    assert Reenvido(2) in legales and Reenvido(38) in legales  # 2 + 38 = 40
    assert Reenvido(1) not in legales and Reenvido(39) not in legales
    assert Paso() not in legales and Envido() not in legales


def test_todos_pasan_y_recuento():
    s = jugar(preparar(), *pasan(4), *pasan(4), *pasan(2))
    resumen = s.manos_jugadas[-1]
    # A: grande en paso 1 + par de reyes 1 + juego 37 (2) = 4. B: chica en paso 1.
    assert resumen.tantos == (4, 1)
    assert s.tantos == [4, 1]
    assert s.numero_mano == 2 and s.mano == 1  # la mano rota
    assert s.fase is Fase.MUS and s.turno == 1


def test_envite_querido_se_cobra_en_el_recuento():
    s = jugar(preparar(), Envido(5), Quiero())
    assert s.lance is Lance.CHICA
    assert s.tantos == [0, 0]  # todavía no se cobra
    s = jugar(s, *pasan(4), *pasan(2))
    # A: grande 5 + par 1 + juego 2 = 8. B: chica en paso 1.
    assert s.manos_jugadas[-1].tantos == (8, 1)


def test_no_quiero_de_los_dos_rivales_cobra_uno_en_el_momento():
    s = jugar(preparar(), Envido(), NoQuiero())
    assert s.turno == 3  # habla el compañero
    s = apply(s, NoQuiero())
    assert s.tantos == [1, 0]
    assert s.lance is Lance.CHICA
    assert s.resultados[-1].tipo is TipoResultado.NO_QUERIDO


def test_basta_con_que_uno_quiera():
    s = jugar(preparar(), Envido(), NoQuiero(), Quiero())
    assert s.resultados[-1].tipo is TipoResultado.QUERIDO
    assert s.resultados[-1].apuesta == 2


def test_el_total_de_la_apuesta_no_pasa_de_40():
    s = jugar(preparar(), Envido(30))
    legales = legal_actions(s)
    assert Reenvido(10) in legales and Reenvido(11) not in legales
    s = jugar(s, Reenvido(10))
    assert s.apuesta.tantos == 40
    assert not any(isinstance(a, Reenvido) for a in legal_actions(s))
    assert Ordago() in legal_actions(s)


def test_sin_sitio_para_un_reenvido_de_2():
    s = jugar(preparar(), Envido(39))
    assert not any(isinstance(a, Reenvido) for a in legal_actions(s))
    with pytest.raises(IllegalActionError):
        apply(s, Reenvido(2))


def test_reenvido_no_querido_cobra_la_apuesta_anterior():
    s = jugar(preparar(), Envido(), Reenvido(5))
    assert s.apuesta.tantos == 7 and s.turno == 0
    s = jugar(s, NoQuiero(), NoQuiero())
    assert s.tantos == [0, 2]


def test_reenvido_querido():
    s = jugar(preparar(), Envido(3), Reenvido(4), Quiero(), *pasan(4), *pasan(2))
    # A gana la grande (7) + par 1 + juego 2. B: chica 1.
    assert s.manos_jugadas[-1].tantos == (10, 1)


def test_ordago_querido_gana_la_vaca():
    s = jugar(preparar(), Ordago(), Quiero())
    assert s.vacas == [1, 0]
    assert s.tantos == [0, 0]
    assert s.manos_jugadas[-1].ganador_vaca == 0
    assert s.mano == 1 and s.fase is Fase.MUS


def test_ordago_querido_lo_gana_quien_gana_el_lance():
    s = jugar(preparar(), Paso(), Paso(), Paso(), Paso(), Ordago(), Quiero())
    assert s.vacas == [0, 1]  # la chica la gana el asiento 1


def test_ordago_no_querido():
    s = jugar(preparar(), Ordago(), NoQuiero(), NoQuiero())
    assert s.tantos == [1, 0] and s.vacas == [0, 0]


def test_ordago_como_reenvido_solo_admite_quiero_o_no_quiero():
    s = jugar(preparar(), Envido(3), Ordago())
    assert set(legal_actions(s)) == {Quiero(), NoQuiero()}
    s = jugar(s, NoQuiero(), NoQuiero())
    assert s.tantos == [0, 3]


def test_en_pares_solo_hablan_los_que_tienen():
    s = jugar(preparar(), *pasan(4), *pasan(4))
    assert s.lance is Lance.PARES
    assert s.apuesta.participantes == (0, 1)
    assert s.declaraciones[Lance.PARES] == {0: True, 1: True, 2: False, 3: False}


def test_pares_no_querido_cobra_sus_pares_en_el_recuento():
    s = jugar(preparar(), *pasan(4), *pasan(4), Paso(), Envido(), NoQuiero())
    resumen = s.manos_jugadas[-1]
    pares = [(c.pareja, c.tantos, c.motivo) for c in resumen.cobros if c.lance is Lance.PARES]
    assert pares == [(1, 1, "no quiero"), (1, 1, "par 1")]
    # A: grande 1 + juego 2. B: chica 1 + no quiero 1 + su par de ases 1.
    assert resumen.tantos == (3, 3)


def test_juego_con_una_sola_pareja_no_tiene_apuestas():
    s = jugar(preparar(), *pasan(4), *pasan(4), *pasan(2))
    juego = s.manos_jugadas[-1]
    cobro = [c for c in juego.cobros if c.lance is Lance.JUEGO][0]
    assert cobro.pareja == 0 and cobro.tantos == 2


def test_juego_con_las_dos_parejas_y_bonus():
    manos = ["R C S A", "R R C 7", "4 5 6 7", "A A 4 5"]  # 31 (A) contra 37 (B)
    s = jugar(preparar(manos), *pasan(4), *pasan(4))
    # pares: solo B (asientos 1 y 3), sin apuesta
    assert s.lance is Lance.JUEGO and s.apuesta.participantes == (0, 1)
    s = jugar(s, Envido(), Quiero())
    cobros = {c.lance: c for c in s.manos_jugadas[-1].cobros}
    assert cobros[Lance.JUEGO].pareja == 0
    assert cobros[Lance.JUEGO].tantos == 2 + 3  # envite + la 31


def test_punto_si_nadie_tiene_juego():
    manos = ["R C 7 2", "R C 5 4", "A A 4 5", "S 6 5 4"]  # 28, 29, 11, 25
    s = jugar(preparar(manos), *pasan(4), *pasan(4))
    assert s.lance is Lance.PUNTO
    s = jugar(s, *pasan(4))
    cobros = {c.lance: c for c in s.manos_jugadas[-1].cobros}
    assert cobros[Lance.PUNTO].pareja == 1 and cobros[Lance.PUNTO].tantos == 1


def test_punto_envite_querido():
    manos = ["R C 7 2", "R C 5 4", "A A 4 5", "S 6 5 4"]
    s = jugar(preparar(manos), *pasan(4), *pasan(4), Envido(4), Quiero())
    cobros = {c.lance: c for c in s.manos_jugadas[-1].cobros}
    assert cobros[Lance.PUNTO].pareja == 1 and cobros[Lance.PUNTO].tantos == 5


def test_empate_en_grande_gana_la_mano():
    iguales = ["R C 7 A", "R C 7 A", "R C 7 A", "R C 7 A"]
    s = jugar(preparar(iguales, mano_inicial=1), *pasan(4), *pasan(4), *pasan(4))
    cobros = {c.lance: c for c in s.manos_jugadas[-1].cobros}
    assert cobros[Lance.GRANDE].pareja == 1
    assert cobros[Lance.CHICA].pareja == 1


# --- Fin de vaca y de partida ---


def test_recuento_se_para_al_llegar_a_40():
    s = jugar(preparar(tantos=(38, 38)), *pasan(4), *pasan(4), *pasan(2))
    resumen = s.manos_jugadas[-1]
    # grande A (39), chica B (39), pares A (40): gana A y el juego ya no se cuenta.
    assert resumen.ganador_vaca == 0
    assert resumen.tantos == (40, 39)
    assert [c.lance for c in resumen.cobros] == [Lance.GRANDE, Lance.CHICA, Lance.PARES]
    assert s.vacas == [1, 0] and s.tantos == [0, 0]


def test_no_quiero_que_llega_a_40_gana_la_vaca_en_el_momento():
    s = jugar(preparar(tantos=(39, 0)), Envido(), NoQuiero(), NoQuiero())
    assert s.vacas == [1, 0] and s.tantos == [0, 0]
    assert s.numero_mano == 2


def test_mejor_de_3_termina_con_dos_vacas():
    s = jugar(preparar(vacas=(1, 0)), Ordago(), Quiero())
    assert s.fase is Fase.FIN and s.ganador == 0
    assert legal_actions(s) == []
    with pytest.raises(IllegalActionError):
        apply(s, Mus())


def test_mejor_de_5_necesita_tres_vacas():
    s = jugar(preparar(vacas=(1, 0), mejor_de=5), Ordago(), Quiero())
    assert s.fase is Fase.MUS and s.vacas == [2, 0]
    s = preparar(vacas=(2, 1), mejor_de=5)
    s = jugar(s, Ordago(), Quiero())
    assert s.fase is Fase.FIN and s.ganador == 0 and s.vacas == [3, 1]


# --- Jugadas ilegales ---


@pytest.mark.parametrize(
    "accion",
    [Paso(), Quiero(), Envido(), Descarte(frozenset()), None, "mus"],
)
def test_accion_ilegal_en_fase_de_mus(accion):
    s = nueva_partida(seed=2)
    antes = huella(s)
    with pytest.raises(IllegalActionError):
        apply(s, accion)
    assert huella(s) == antes


@pytest.mark.parametrize(
    "accion",
    [Envido(1), Envido(41), Reenvido(3), Quiero(), NoQuiero(), Mus(), NoHayMus()],
)
def test_accion_ilegal_en_apuestas(accion):
    s = preparar()
    antes = huella(s)
    with pytest.raises(IllegalActionError):
        apply(s, accion)
    assert huella(s) == antes


def test_descarte_ilegal():
    s = jugar(nueva_partida(seed=3), Mus(), Mus(), Mus(), Mus())
    ajena = next(c for c in s.cartas[1] if c not in s.cartas[0])
    antes = huella(s)
    with pytest.raises(IllegalActionError):
        apply(s, Descarte(frozenset({ajena})))
    with pytest.raises(IllegalActionError):
        apply(s, Descarte(frozenset()))
    with pytest.raises(IllegalActionError):
        apply(s, Descarte(frozenset({*s.cartas[0][:1], ajena})))
    assert huella(s) == antes


def test_apply_no_modifica_el_estado_original():
    s = preparar()
    antes = huella(s)
    nuevo = apply(s, Envido())
    assert huella(s) == antes
    assert nuevo is not s and nuevo.apuesta.tantos == 2 and s.apuesta.tantos == 0

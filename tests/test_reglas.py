"""Reglas de ``docs/reglas.md`` que no tenían un test directo (hallazgo B22 de la auditoría).

Cada test prepara una mano con cartas concretas, juega las acciones y comprueba números: los
tantos que cobra cada pareja, quién gana la vaca y a quién le toca hablar. Las secciones de
``docs/reglas.md`` que se comprueban van en el docstring de cada test.

Asientos: el Jugador N es el asiento ``N-1``; la pareja A (0) son los asientos 0 y 2 y la
pareja B (1) los asientos 1 y 3.
"""

from helpers import mano
from musarena.actions import Envido, NoHayMus, NoQuiero, Ordago, Paso, Quiero, Reenvido
from musarena.engine import apply, nueva_partida
from musarena.hands import Lance
from musarena.state import Fase, TipoResultado

A, B = 0, 1


def preparar(manos, mano_inicial=0):
    """Estado recién cortado el mus, con las manos indicadas (16 cartas distintas)."""
    s = nueva_partida(seed=0, mano=mano_inicial)
    s.cartas = [mano(t) for t in manos]
    todas = [c for cartas in s.cartas for c in cartas]
    assert len(set(todas)) == 16, "las manos de un test no pueden repetir cartas"
    return apply(s, NoHayMus())


def jugar(s, *acciones):
    for a in acciones:
        s = apply(s, a)
    return s


def pasan(n):
    return [Paso()] * n


def cobros(s, lance):
    """(pareja, tantos, motivo) de los cobros de un lance en la última mano terminada."""
    return [(c.pareja, c.tantos, c.motivo) for c in s.manos_jugadas[-1].cobros
            if c.lance is lance]


# --- 1. Medias y duples: la pareja ganadora suma los pares de sus dos jugadores ---------------

# Mano el asiento 0. Pares: medias de reyes (0), par de ases (1), duples (2); el 3 no tiene.
# Juego: solo la pareja A (37 y 40), sin apuesta.
MEDIAS_Y_DUPLES = ["Ro Rc Re 7o", "Ac Ae 4c 5c", "Co Cc So Sc", "Cb 7b 6b 4b"]


def test_pares_en_paso_suma_medias_y_duples_de_la_pareja():
    """§6 Recuento (pares: par 1, medias 2, duples 3, de los dos jugadores) y §4 Pares."""
    s = jugar(preparar(MEDIAS_Y_DUPLES), *pasan(4), *pasan(4))
    assert s.lance is Lance.PARES and s.apuesta.participantes == (0, 1, 2)
    s = jugar(s, *pasan(3))
    # Gana A (duples del asiento 2) y cobra las medias del 0 (2) + los duples del 2 (3).
    assert cobros(s, Lance.PARES) == [(A, 5, "medias 2 + duples 3")]


def test_pares_querido_suma_la_apuesta_y_los_pares_de_los_dos():
    """§6 Recuento: pares = apuesta aceptada + pares de los dos jugadores de la pareja."""
    s = jugar(preparar(MEDIAS_Y_DUPLES), *pasan(4), *pasan(4), Envido(4), Quiero())
    assert cobros(s, Lance.PARES) == [(A, 4 + 2 + 3, "envite 4 + medias 2 + duples 3")]


def test_pares_sin_apuesta_tambien_suma_los_de_los_dos():
    """§4 Pares (si solo una pareja tiene, se lleva los tantos sin apuesta) y §6 Recuento."""
    manos = ["Ro Rc Re 7o", "Ac 6e 4c 5c", "Co Cc So Sc", "Cb 7b 6b 4b"]  # el 1 ya no tiene
    s = jugar(preparar(manos), *pasan(4), *pasan(4))
    assert s.numero_mano == 2  # sin apuestas en pares ni en juego: la mano ya ha terminado
    assert cobros(s, Lance.PARES) == [(A, 5, "medias 2 + duples 3")]


# --- 2. "No quiero" en juego y en punto -------------------------------------------------------

# Mano el asiento 0. Nadie tiene pares. Juego: 31 (0), 37 (1), 31 (3); el 2 no tiene (22).
# La pareja B tiene peor juego que A (el 31 del asiento 0 es el mejor y gana los empates).
JUEGO = ["Ro Co So Ao", "Rc Cc Sc 7c", "4e 5e 6e 7e", "Rb Cb Sb Ab"]


def test_juego_no_querido_cobra_uno_en_el_momento_y_sus_juegos_sin_comparar():
    """§5 (no quiero: 1 tanto si era la primera apuesta, cobrado en el momento) y §6
    Aclaraciones (en juego la pareja que envidó cobra sus juegos sin compararlos)."""
    s = jugar(preparar(JUEGO), *pasan(4), *pasan(4))
    assert s.lance is Lance.JUEGO and s.apuesta.participantes == (0, 1, 3)
    s = jugar(s, Paso(), Envido())
    assert s.turno == 0  # de la pareja A solo habla el asiento 0, el único con juego
    s = apply(s, NoQuiero())
    # El lance acaba: era el último, así que la mano termina y se reparte la siguiente.
    assert s.numero_mano == 2 and s.fase is Fase.MUS and s.turno == 1
    # B cobra 1 en el momento y en el recuento su 37 (2) y su 31 (3); A no cobra su 31.
    assert cobros(s, Lance.JUEGO) == [(B, 1, "no quiero"), (B, 5, "juego 2 + juego 3")]
    lances = [c.lance for c in s.manos_jugadas[-1].cobros]
    assert lances[0] is Lance.JUEGO  # el no quiero se cobra antes del recuento


def test_juego_reenvido_no_querido_cobra_la_apuesta_anterior():
    """§5 (no quiero a un reenvido: la apuesta anterior) y §6 Aclaraciones (sus juegos)."""
    s = jugar(preparar(JUEGO), *pasan(4), *pasan(4), Envido())
    assert s.turno == 1  # responde primero el rival más cercano a la mano
    s = jugar(s, Reenvido(3))
    assert s.apuesta.tantos == 5 and s.turno == 0
    s = apply(s, NoQuiero())
    assert s.numero_mano == 2
    assert cobros(s, Lance.JUEGO) == [(B, 2, "no quiero"), (B, 5, "juego 2 + juego 3")]


# Mano el asiento 0. Nadie tiene juego: punto 30 (0), 29 (1), 16 (2), 17 (3). Nadie tiene pares.
PUNTO = ["Ro Co 6o 4o", "Rc Cc 5c 4c", "Ae 4e 5e 6e", "Ab 4b 5b 7b"]


def test_punto_no_querido_cobra_uno_en_el_momento_y_el_tanto_del_punto():
    """§5 (no quiero: 1 tanto, en el momento; si dice no quiero, habla el compañero) y §6
    Aclaraciones (en punto la pareja que envidó cobra el tanto del punto sin comparar)."""
    s = jugar(preparar(PUNTO), *pasan(4), *pasan(4))
    assert s.lance is Lance.PUNTO and s.apuesta.participantes == (0, 1, 2, 3)
    s = jugar(s, Paso(), Envido())  # envida B, que tiene peor punto (29 contra 30)
    assert s.turno == 0  # responde primero la mano
    s = apply(s, NoQuiero())
    assert s.turno == 2 and s.lance is Lance.PUNTO  # el lance sigue: falta el compañero
    assert s.tantos == [0, 0]
    s = apply(s, NoQuiero())
    assert s.numero_mano == 2 and s.fase is Fase.MUS
    assert cobros(s, Lance.PUNTO) == [(B, 1, "no quiero"), (B, 1, "punto 1")]
    assert s.manos_jugadas[-1].cobros[0].lance is Lance.PUNTO


def test_punto_reenvido_no_querido_cobra_la_apuesta_anterior():
    """§5: no quiero a un reenvido cobra la apuesta anterior; §6: más el tanto del punto."""
    s = jugar(preparar(PUNTO), *pasan(4), *pasan(4), Envido(3), Reenvido(5))
    assert s.apuesta.tantos == 8 and s.turno == 0
    s = jugar(s, NoQuiero(), NoQuiero())
    assert cobros(s, Lance.PUNTO) == [(B, 3, "no quiero"), (B, 1, "punto 1")]


# --- 3. Órdago aceptado en pares, juego y punto -----------------------------------------------


def test_ordago_a_pares_lo_gana_la_mejor_jugada():
    """§5 (órdago aceptado: quien gane ese lance gana la vaca) y §4 Pares (medias > par)."""
    # La pareja A gana la grande (reyes), pero en pares tiene par y B tiene medias.
    manos = ["Ro Rc 7o 4o", "Ce Cb Cc 4c", "Se 6e 5e Ae", "Sb 7b 6b Ab"]
    s = jugar(preparar(manos), *pasan(4), *pasan(4))
    assert s.lance is Lance.PARES and s.apuesta.participantes == (0, 1)
    s = jugar(s, Ordago(), Quiero())
    assert s.vacas == [0, 1] and s.tantos == [0, 0]
    assert s.manos_jugadas[-1].ganador_vaca == B
    assert cobros(s, Lance.PARES) == [(B, 0, "órdago aceptado: gana la vaca")]
    assert len(s.manos_jugadas[-1].cobros) == 1  # la mano termina: no hay recuento


def test_ordago_a_pares_empatado_lo_gana_el_mas_cercano_a_la_mano():
    """§4 Empates: par de reyes contra par de reyes; gana el más cercano a la mano."""
    manos = ["Ro Rc 7o 4o", "Re Rb 6c 5c", "Ce Se 6e 5e", "Cb Sb 7b Ab"]
    s = jugar(preparar(manos, mano_inicial=1), *pasan(4), *pasan(4))
    assert s.lance is Lance.PARES and s.apuesta.participantes == (1, 0)
    s = jugar(s, Paso(), Ordago(), Quiero())  # echa el órdago A; quiere el asiento 1 (mano)
    assert s.vacas == [0, 1]


def test_ordago_a_juego_lo_gana_la_31():
    """§5 (órdago aceptado) y §4 Juego (31 es el mejor juego, aunque 37 sume más)."""
    s = jugar(preparar(JUEGO), *pasan(4), *pasan(4))
    s = jugar(s, Paso(), Ordago(), Quiero())  # órdago de B (37 y 31), quiere el 0 (31)
    # Los dos tienen 31 (asientos 0 y 3): el empate es del 0, más cercano a la mano.
    assert s.vacas == [1, 0]
    assert s.manos_jugadas[-1].ganador_vaca == A


def test_ordago_a_juego_empatado_lo_gana_el_mas_cercano_a_la_mano():
    """§4 Empates: 31 contra 31; con mano el asiento 1, gana la pareja B."""
    manos = ["Ro Co So Ao", "Rc Cc 7c 4c", "4e 5e 6e 7e", "4b 5b 6b Ab"]
    s = jugar(preparar(manos, mano_inicial=1), *pasan(4), *pasan(4))
    assert s.lance is Lance.JUEGO and s.apuesta.participantes == (1, 0)
    s = jugar(s, Paso(), Ordago(), Quiero())
    assert s.vacas == [0, 1]


def test_ordago_al_punto_lo_gana_el_mas_cercano_a_30():
    """§5 (órdago aceptado) y §4 Juego (al punto gana quien más se acerca a 30)."""
    s = jugar(preparar(PUNTO), *pasan(4), *pasan(4), Paso(), Ordago())
    assert s.turno == 0
    s = jugar(s, NoQuiero(), Quiero())  # basta con que quiera el compañero
    assert s.vacas == [1, 0]  # 30 del asiento 0 contra 29 del asiento 1


def test_ordago_al_punto_empatado_lo_gana_el_mas_cercano_a_la_mano():
    """§4 Empates: 30 contra 30; con mano el asiento 1, gana la pareja B."""
    manos = ["Ro Co 6o 4o", "Rc Cc 6c 4c", "Ae 4e 5e 6e", "Ab 4b 5b 7b"]
    s = jugar(preparar(manos, mano_inicial=1), *pasan(4), *pasan(4))
    assert s.lance is Lance.PUNTO
    s = jugar(s, Ordago(), Quiero())  # órdago del 1 (mano); quiere el 2
    assert s.vacas == [0, 1]


# --- 4. Reenvites encadenados y rechazados ----------------------------------------------------

# Mano el asiento 0. La grande la gana A (asiento 0).
GRANDE = ["Ro Rc Co 7o", "Ac Ae 4c 5c", "Se 6e 5e 4e", "Cb 7b 6b 4b"]


def test_cadena_de_reenvidos_no_querida_cobra_la_apuesta_anterior_a_la_ultima_subida():
    """§5: no quiero a un reenvido cobra la apuesta anterior (lo que había antes)."""
    s = jugar(preparar(GRANDE), Envido(2), Reenvido(3), Reenvido(4))
    assert s.apuesta.tantos == 9 and s.apuesta.pareja_apostadora == A
    s = jugar(s, Reenvido(5))  # B sube a 14
    assert s.apuesta.tantos == 14 and s.apuesta.deje == 9 and s.turno == 0
    s = jugar(s, NoQuiero(), NoQuiero())
    assert s.tantos == [0, 9]  # cobrado en el momento
    assert s.lance is Lance.CHICA
    assert s.resultados[-1].tipo is TipoResultado.NO_QUERIDO and s.resultados[-1].pareja == B


def test_cadena_de_reenvidos_no_querida_por_la_otra_pareja():
    """§5: la misma cadena cortada una subida antes: A apostó la última y cobra 5."""
    s = jugar(preparar(GRANDE), Envido(2), Reenvido(3), Reenvido(4), NoQuiero(), NoQuiero())
    assert s.tantos == [5, 0] and s.lance is Lance.CHICA


def test_ordago_sobre_reenvido_no_querido_cobra_la_apuesta_anterior():
    """§5: un órdago como subida rechazado cobra lo que había apostado antes."""
    s = jugar(preparar(GRANDE), Envido(2), Reenvido(3), Ordago(), NoQuiero(), NoQuiero())
    assert s.tantos == [5, 0] and s.vacas == [0, 0]


def test_reenvidos_en_pares_no_queridos_cobran_la_apuesta_anterior_y_sus_pares():
    """§5 (cadena de reenvidos, responde el compañero) y §6 (no quiero: además sus pares)."""
    s = jugar(preparar(MEDIAS_Y_DUPLES), *pasan(4), *pasan(4), Envido(2))
    assert s.turno == 1  # de B solo tiene pares el asiento 1
    s = jugar(s, Reenvido(3))
    assert s.turno == 0
    s = jugar(s, NoQuiero())
    assert s.turno == 2  # habla el compañero, que también tiene pares
    s = jugar(s, Reenvido(4))
    assert s.apuesta.tantos == 9 and s.turno == 1
    s = jugar(s, NoQuiero())  # nadie más de B tiene pares: el no quiero cierra el lance
    assert cobros(s, Lance.PARES) == [(A, 5, "no quiero"), (A, 5, "medias 2 + duples 3")]


# --- 5. Orden de respuesta cuando apuesta quien no es mano ------------------------------------


def test_si_envida_el_segundo_responde_primero_la_mano():
    """§5 Aclaraciones: responde primero el rival más cercano a la mano; luego su compañero."""
    s = jugar(preparar(GRANDE), Paso(), Envido())  # envida el asiento 1
    assert s.apuesta.por_hablar == [0, 2] and s.turno == 0
    s = apply(s, NoQuiero())
    assert s.turno == 2
    s = apply(s, Quiero())  # basta con que uno quiera
    assert s.resultados[-1].tipo is TipoResultado.QUERIDO and s.resultados[-1].apuesta == 2


def test_si_envida_el_tercero_responde_primero_el_segundo():
    """§5 Aclaraciones: con mano el 0, si envida el 2 responde el 1 antes que el 3."""
    s = jugar(preparar(GRANDE), Paso(), Paso(), Envido())
    assert s.turno == 1
    s = jugar(s, NoQuiero())
    assert s.turno == 3
    s = jugar(s, NoQuiero())
    assert s.tantos == [1, 0] and s.lance is Lance.CHICA


def test_si_envida_el_postre_responde_primero_la_mano():
    """§5 Aclaraciones: el postre (asiento 3) envida; responde la mano (0) y luego el 2."""
    s = jugar(preparar(GRANDE), *pasan(3), Envido())
    assert s.turno == 0
    s = jugar(s, NoQuiero(), NoQuiero())
    assert s.tantos == [0, 1]


def test_orden_de_respuesta_con_la_mano_en_otro_asiento():
    """§5 Aclaraciones: con mano el asiento 2, si envida el 3 responde el 2 y luego el 0."""
    s = jugar(preparar(GRANDE, mano_inicial=2), Paso(), Envido())
    assert s.turno == 2
    s = apply(s, NoQuiero())
    assert s.turno == 0
    s = apply(s, NoQuiero())
    assert s.tantos == [0, 1]


def test_ante_un_reenvido_responde_primero_el_mas_cercano_a_la_mano():
    """§5 Aclaraciones: el 1 envida, la mano reenvida y vuelve a hablar primero el 1."""
    s = jugar(preparar(GRANDE), Paso(), Envido(), Reenvido(2))
    assert s.turno == 1
    s = apply(s, NoQuiero())
    assert s.turno == 3
    s = apply(s, NoQuiero())
    assert s.tantos == [2, 0]


def test_en_pares_si_el_que_responde_no_tiene_companero_con_jugada_se_cierra():
    """§5 Aclaraciones: en pares solo responden los que tienen la jugada; si el único rival
    con pares dice no quiero, no habla su compañero."""
    s = jugar(preparar(MEDIAS_Y_DUPLES), *pasan(4), *pasan(4), Paso(), Paso(), Envido())
    assert s.turno == 1  # el 3 no tiene pares: solo responde el 1
    s = apply(s, NoQuiero())
    assert cobros(s, Lance.PARES) == [(A, 1, "no quiero"), (A, 5, "medias 2 + duples 3")]

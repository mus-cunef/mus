import random

import pytest

from helpers import mano
from musarena.actions import Descarte, Envido, Mus, NoHayMus, Paso, Quiero
from musarena.cards import todas_las_cartas
from musarena.engine import apply, nueva_partida
from musarena.estrategia.creencias import Creencias, ModeloRival, ronda_de_mus, verosimilitud
from musarena.estrategia.evaluacion import (
    bonus_pareja,
    prob_ganar_lance,
    prob_vaca,
    respuesta_rival,
)
from musarena.estrategia.lectura import LectorRivales
from musarena.estrategia.tipos import (
    FUERZA,
    N_TIPOS,
    NIVEL,
    PESOS_BASE,
    TIENE_PARES,
    indice_de,
    pesos_sin,
)
from musarena.estrategia.valor import PERCENTIL, VALOR, valor_tras_descarte
from musarena.hands import Lance, clave, ganador, tiene_pares
from musarena.observation import observe
from musarena.state import Evento, ResumenMano, pareja

# --- Tipos de mano ---


def test_330_tipos_que_cubren_todas_las_manos():
    assert N_TIPOS == 330
    assert PESOS_BASE.sum() == 91_390
    # Sin 4 cartas conocidas quedan C(36, 4) manos posibles.
    assert pesos_sin(mano("R C S A")).sum() == 58_905


@pytest.mark.parametrize("lance", list(Lance))
def test_los_niveles_ordenan_igual_que_las_claves(lance):
    rng = random.Random(1)
    cartas = todas_las_cartas()
    for _ in range(300):
        a, b = rng.sample(cartas, 4), rng.sample(cartas, 4)
        na, nb = NIVEL[lance][indice_de(a)], NIVEL[lance][indice_de(b)]
        ka, kb = clave(lance, a), clave(lance, b)
        assert (na > nb) == (ka > kb) and (na == nb) == (ka == kb)


def test_las_tablas_no_se_pueden_modificar():
    with pytest.raises(ValueError):
        FUERZA[Lance.GRANDE][0] = 1.0


# --- Valor de la mano y descartes ---


def test_percentiles_de_mano():
    assert 0 <= PERCENTIL.min() and PERCENTIL.max() <= 1
    assert PERCENTIL[indice_de(mano("4 5 6 7"))] < 0.01  # la peor mano del mus
    assert PERCENTIL[indice_de(mano("R R R A"))] > 0.99
    assert VALOR[indice_de(mano("R R C C"))] > VALOR[indice_de(mano("R C 7 4"))]


def test_descartar_bien_vale_mas_que_descartar_mal():
    cartas = mano("R 3 7 5")
    bien = valor_tras_descarte(cartas, cartas[2:])  # tira 7 y 5, se queda los reyes
    mal = valor_tras_descarte(cartas, cartas[:2])  # tira los reyes
    assert bien > mal
    assert valor_tras_descarte(cartas, []) == pytest.approx(VALOR[indice_de(cartas)])


# --- Probabilidad de ganar un lance: comparación con una simulación ---


def _simular(lance, mias, asiento, mano_, participantes, condicion=None, n=20_000, seed=3):
    """Reparte al azar las cartas de los demás y cuenta cuántas veces gana la pareja."""
    rng = random.Random(seed)
    resto = [c for c in todas_las_cartas() if c not in mias]
    ganadas = validas = 0
    while validas < n:
        rng.shuffle(resto)
        manos = {asiento: mias}
        otros = [a for a in range(4) if a != asiento]
        for k, a in enumerate(otros):
            manos[a] = resto[4 * k:4 * k + 4]
        if condicion and not condicion(manos):
            continue
        validas += 1
        en_juego = {a: manos[a] for a in participantes}
        ganadas += pareja(ganador(lance, en_juego, mano_)) == pareja(asiento)
    return ganadas / n


@pytest.mark.parametrize(
    ("lance", "texto", "asiento", "mano_"),
    [
        (Lance.GRANDE, "R C 7 4", 0, 0),
        (Lance.GRANDE, "R C 7 4", 3, 0),  # mismo lance hablando el último: pierde los empates
        (Lance.CHICA, "A A 5 6", 1, 2),
        (Lance.PUNTO, "R C 5 4", 2, 0),
    ],
)
def test_prob_ganar_coincide_con_la_simulacion(lance, texto, asiento, mano_):
    mias = mano(texto)
    s = nueva_partida(seed=0, mano=mano_)
    s.cartas[asiento] = mias
    creencias = Creencias.desde_observacion(observe(s, asiento))
    calculada = prob_ganar_lance(lance, asiento, mias, mano_, range(4), creencias)
    simulada = _simular(lance, mias, asiento, mano_, range(4))
    # Tolerancia: error de muestreo más la simplificación de tratar las manos como independientes.
    assert calculada == pytest.approx(simulada, abs=0.03)


def test_prob_ganar_pares_con_declaraciones():
    """Solo juegan los que tienen pares: la creencia se condiciona a las declaraciones."""
    mias = mano("S S 7 4")
    s = nueva_partida(seed=0, mano=0)
    s.cartas[0] = mias
    s.declaraciones[Lance.PARES] = {0: True, 1: True, 2: False, 3: False}
    creencias = Creencias.desde_observacion(observe(s, 0))
    calculada = prob_ganar_lance(Lance.PARES, 0, mias, 0, (0, 1), creencias)

    def declaran(manos):
        return tiene_pares(manos[1]) and not tiene_pares(manos[2]) and not tiene_pares(manos[3])

    simulada = _simular(Lance.PARES, mias, 0, 0, (0, 1), declaran, n=8000)
    assert calculada == pytest.approx(simulada, abs=0.04)


def test_sin_compañero_se_gana_menos():
    mias = mano("C S 7 4")
    creencias = Creencias.desde_observacion(observe(nueva_partida(seed=0), 0))
    con = prob_ganar_lance(Lance.GRANDE, 0, mias, 0, range(4), creencias)
    sin = prob_ganar_lance(Lance.GRANDE, 0, mias, 0, range(4), creencias, incluir_companero=False)
    assert sin < con


# --- Creencias ---


def _en_grande(manos, seed=0):
    s = nueva_partida(seed=seed)
    s.cartas = [mano(t) for t in manos]
    return apply(s, NoHayMus())


def test_creencias_suman_uno_y_excluyen_lo_declarado():
    s = _en_grande(["R R 5 4", "S S 7 4", "4 5 6 7", "C 6 7 A"])
    for _ in range(8):
        s = apply(s, Paso())
    assert s.lance is Lance.PARES
    creencias = Creencias.desde_observacion(observe(s, 0))
    for otro in (1, 2, 3):
        assert creencias.probabilidades(otro).sum() == pytest.approx(1)
    assert creencias.probabilidades(1)[~TIENE_PARES].sum() == 0  # declaró que sí tiene
    assert creencias.probabilidades(2)[TIENE_PARES].sum() == 0  # declaró que no tiene


def test_un_envite_hace_mas_probable_una_mano_fuerte():
    s = _en_grande(["4 5 6 A", "R R R C", "4 5 6 7", "4 5 6 7"])
    antes = Creencias.desde_observacion(observe(s, 0))
    s = apply(apply(s, Paso()), Envido(5))  # el asiento 1 envida a grande
    despues = Creencias.desde_observacion(observe(s, 0))
    fuerza_media = [c.esperanza(1, FUERZA[Lance.GRANDE]) for c in (antes, despues)]
    assert fuerza_media[1] > fuerza_media[0] + 0.1
    # Del compañero, que no ha hablado, no se sabe nada nuevo.
    assert despues.esperanza(3, FUERZA[Lance.GRANDE]) == pytest.approx(
        antes.esperanza(3, FUERZA[Lance.GRANDE])
    )


def test_quien_corta_el_mus_suele_tener_buena_mano():
    s = apply(apply(nueva_partida(seed=4), Mus()), NoHayMus())  # el 0 pide mus, el 1 corta
    ronda = ronda_de_mus(s.historial)
    assert [type(e.accion) for e in ronda] == [Mus, NoHayMus]
    creencias = Creencias.desde_observacion(observe(s, 2))
    assert creencias.esperanza(1, PERCENTIL) > creencias.esperanza(0, PERCENTIL) + 0.1


def test_la_ronda_de_mus_es_la_ultima():
    s = nueva_partida(seed=4)
    for _ in range(4):
        s = apply(s, Mus())
    for _ in range(4):
        s = apply(s, Descarte(frozenset(s.cartas[s.turno][:1])))
    s = apply(s, NoHayMus())
    assert [e.asiento for e in ronda_de_mus(s.historial)] == [0]


def test_querer_es_mas_probable_con_mano_fuerte():
    modelo = ModeloRival()
    assert verosimilitud(Quiero(), 0.9, modelo) > verosimilitud(Quiero(), 0.2, modelo)
    # Un envite que decide la vaca exige más mano para quererlo.
    assert verosimilitud(Quiero(), 0.6, modelo, apuesta=30, faltan=30) < verosimilitud(
        Quiero(), 0.6, modelo, apuesta=2, faltan=30
    )


def test_respuesta_rival():
    s = _en_grande(["R R C 7", "4 5 6 7", "5 6 7 A", "4 5 6 A"])
    obs = observe(s, 0)
    creencias = Creencias.desde_observacion(obs)
    p = prob_ganar_lance(Lance.GRANDE, 0, obs.cartas, 0, range(4), creencias)
    q, p_si = respuesta_rival(Lance.GRANDE, 0, obs.cartas, 0, range(4), creencias,
                              ModeloRival(), apuesta=5)
    assert 0 < q < 1
    assert p_si < p  # si me quieren es porque tienen mano


def test_bonus_de_pareja():
    s = _en_grande(["R R 5 4", "S S 7 4", "4 5 6 7", "C 6 7 A"])
    for _ in range(8):
        s = apply(s, Paso())
    obs = observe(s, 0)
    creencias = Creencias.desde_observacion(obs)
    assert bonus_pareja(Lance.PARES, 0, 0, obs.cartas, (0, 1), creencias) == 1  # mi par
    assert bonus_pareja(Lance.PARES, 1, 0, obs.cartas, (0, 1), creencias) >= 1
    assert bonus_pareja(Lance.GRANDE, 0, 0, obs.cartas, range(4), creencias) == 0
    assert bonus_pareja(Lance.PUNTO, 0, 0, obs.cartas, range(4), creencias) == 1


# --- Probabilidad de ganar la vaca ---


def test_prob_vaca():
    assert prob_vaca(0, 0) == pytest.approx(0.5)
    assert prob_vaca(20, 20) == pytest.approx(0.5)
    assert prob_vaca(40, 10) == 1 and prob_vaca(10, 40) == 0
    assert prob_vaca(30, 0) > prob_vaca(20, 0) > prob_vaca(10, 0) > 0.5
    assert prob_vaca(0, 30) == pytest.approx(1 - prob_vaca(30, 0))


# --- Lectura de rivales ---


def _resumen_con(acciones, cartas):
    historial = tuple(Evento(a, str(x), x, Lance.GRANDE) for a, x in acciones)
    return ResumenMano(1, 0, tuple(tuple(mano(c)) for c in cartas), (), (0, 0), None, historial)


def test_lector_detecta_a_quien_va_de_farol():
    lector = LectorRivales()
    cartas = ["R R R C", "4 5 6 A", "R R C S", "4 5 6 7"]  # el 1 y el 3 llevan grande floja
    for _ in range(10):
        lector.registrar(_resumen_con([(1, Envido()), (3, Paso())], cartas), asiento_propio=0)
    previa = ModeloRival().farol
    assert lector.tasa_farol(1, previa) > 0.4  # envida siempre sin mano
    assert lector.tasa_farol(3, previa) < previa  # nunca va de farol
    assert lector.tasa_farol(2, previa) == pytest.approx(previa)  # sin datos: la previa
    modelos = lector.modelos(ModeloRival(), asiento_propio=0)
    assert set(modelos) == {1, 2, 3} and modelos[1].farol > modelos[3].farol

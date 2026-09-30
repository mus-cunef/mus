import random

import numpy as np
import pytest

from helpers import JugadorAleatorio
from musarena.actions import Envido, NoHayMus, Reenvido
from musarena.arena import enfrentar
from musarena.engine import apply, legal_actions, nueva_partida
from musarena.ia import acciones
from musarena.ia.codificacion import N_ENTRADAS, NOMBRES, codificar
from musarena.ia.red import Red
from musarena.match import Match
from musarena.observation import observe
from musarena.players import SmartBot, crear_jugador

# --- Catálogo de acciones ---


def test_catalogo():
    assert acciones.N_ACCIONES == len(acciones.NOMBRES) == 40
    assert len(acciones.DESCARTES) == 15


def test_cada_accion_legal_tiene_su_sitio_en_el_catalogo():
    """En partidas reales, toda acción legal del catálogo se traduce y vuelve igual."""
    for seed in range(3):
        match = Match([JugadorAleatorio(seed=seed * 4 + i) for i in range(4)], seed=seed)
        while not match.terminada:
            s = match.state
            legales = legal_actions(s)
            cartas = s.cartas[s.turno]
            m = acciones.mascara(legales, cartas)
            assert m.any()
            for i in np.flatnonzero(m):
                a = acciones.accion(int(i), cartas)
                assert a in legales
                assert acciones.indice(a, cartas) == i
            match.step()


def test_cantidades_fuera_del_catalogo_van_a_la_mas_cercana():
    cartas = nueva_partida(seed=0).cartas[0]
    assert acciones.NOMBRES[acciones.indice(Envido(7), cartas)] == "Envido 6"
    assert acciones.NOMBRES[acciones.indice(Envido(40), cartas)] == "Envido 30"
    assert acciones.NOMBRES[acciones.indice(Reenvido(12), cartas)] == "Reenvido 10"


def test_la_mascara_respeta_el_tope_de_40():
    s = apply(apply(nueva_partida(seed=0), NoHayMus()), Envido(30))
    m = acciones.mascara(legal_actions(s), s.cartas[s.turno])
    nombres = [acciones.NOMBRES[i] for i in np.flatnonzero(m)]
    reenvidos = [n for n in nombres if "Reenvido" in n]
    assert reenvidos == ["Reenvido 2", "Reenvido 3", "Reenvido 4", "Reenvido 5", "Reenvido 6",
                         "Reenvido 8", "Reenvido 10"]


# --- Codificación ---


def test_codificacion_de_tamano_fijo_y_valores_acotados():
    match = Match([JugadorAleatorio(seed=i) for i in range(4)], seed=1)
    for _ in range(200):
        if match.terminada:
            break
        x = codificar(match.observation(match.state.turno))
        assert x.shape == (N_ENTRADAS,) and x.dtype == np.float32
        assert np.isfinite(x).all() and x.min() >= -1e-6 and x.max() <= 1 + 1e-6
        match.step()
    assert len(NOMBRES) == N_ENTRADAS and len(set(NOMBRES)) == N_ENTRADAS


def test_la_codificacion_no_depende_de_las_cartas_ajenas():
    """Si se cambian las manos de los demás, lo que ve la red no cambia: no hay trampa."""
    s = apply(nueva_partida(seed=5), NoHayMus())
    base = codificar(observe(s, 0))
    otra = s.copiar()
    otra.cartas[1], otra.cartas[3] = otra.cartas[3], otra.cartas[1]
    otra.cartas[2] = list(reversed(otra.cartas[2]))
    assert np.array_equal(base, codificar(observe(otra, 0)))


def test_la_codificacion_es_relativa_al_asiento():
    s = nueva_partida(seed=6)
    x0 = dict(zip(NOMBRES, codificar(observe(s, 0)), strict=True))
    x1 = dict(zip(NOMBRES, codificar(observe(s, 1)), strict=True))
    assert x0["posicion_desde_mano=0"] == 1 and x1["posicion_desde_mano=1"] == 1


# --- Red y bot inteligente ---


def test_red_guardar_y_cargar(tmp_path):
    red = Red.aleatoria(N_ENTRADAS, acciones.N_ACCIONES, ocultas=(32, 16))
    red.guardar(tmp_path / "red.npz")
    otra = Red.cargar(tmp_path / "red.npz")
    x = np.random.default_rng(0).random(N_ENTRADAS).astype(np.float32)
    m = np.ones(acciones.N_ACCIONES, dtype=bool)
    m[:5] = False
    p1, v1 = red.evaluar(x, m)
    p2, v2 = otra.evaluar(x, m)
    assert np.allclose(p1, p2) and v1 == pytest.approx(v2)
    assert p1[:5].sum() == 0 and p1.sum() == pytest.approx(1)
    assert otra.info == {"origen": "aleatoria"}


def test_el_bot_inteligente_juega_partidas_legales():
    for temperatura in (0.0, 1.0):
        mesa = [crear_jugador("inteligente", seed=i, temperatura=temperatura) for i in range(2)]
        mesa += [crear_jugador("reglas", seed=9), crear_jugador("random", seed=9)]
        mesa = [mesa[0], mesa[2], mesa[1], mesa[3]]
        assert Match(mesa, seed=3).play(max_turnos=50_000) in (0, 1)


def test_el_bot_inteligente_explica_su_jugada():
    bot = SmartBot(seed=0)
    s = nueva_partida(seed=2)
    bot.choose_action(observe(s, 0), legal_actions(s))
    assert "valor" in bot.razon and "%" in bot.razon


def test_un_modelo_incompatible_se_detecta():
    with pytest.raises(ValueError):
        SmartBot(modelo=Red.aleatoria(N_ENTRADAS + 1, acciones.N_ACCIONES))


def test_el_modelo_incluido_juega_como_su_maestro():
    """El modelo entrenado por imitación gana claramente al bot básico."""
    assert enfrentar("inteligente", "basico", partidas=100, seed=4).porcentaje_a > 0.6


# --- Entrenamiento (solo si PyTorch está instalado) ---


def test_generar_datos_y_entrenar(tmp_path):
    torch = pytest.importorskip("torch")
    from musarena.ia.entrenamiento import datos, imitacion

    d = datos.generar(4, tipos=("reglas", "random"), seed=1, procesos=1)
    n = len(d["y"])
    assert d["x"].shape == (n, N_ENTRADAS) and d["mascara"].shape == (n, acciones.N_ACCIONES)
    assert d["mascara"][np.arange(n), d["y"]].all()  # la acción elegida siempre era legal
    assert set(np.unique(d["valor"])) <= {-1.0, 1.0}
    datos.guardar(d, tmp_path / "d.npz")
    assert np.allclose(datos.cargar(tmp_path / "d.npz")["x"], d["x"], atol=1e-3)

    modelo, metricas = imitacion.entrenar(d, ocultas=(32,), epocas=2, lote=256, informar=False)
    assert 0 <= metricas["aciertos"] <= 1
    red = modelo.a_numpy({"origen": "test"})
    # La red de numpy da lo mismo que la de PyTorch.
    i = random.Random(0).randrange(n)
    x, m = torch.from_numpy(d["x"][i:i + 1]), torch.from_numpy(d["mascara"][i:i + 1])
    with torch.no_grad():
        logits, valor = modelo(x, m)
    p, v = red.evaluar(d["x"][i], d["mascara"][i])
    assert np.allclose(p, torch.softmax(logits, 1).numpy()[0], atol=1e-5)
    assert v == pytest.approx(float(valor[0]), abs=1e-5)
    otra = imitacion.RedTorch.desde_numpy(red)
    with torch.no_grad():
        logits2, _ = otra(x, m)
    assert torch.allclose(logits, logits2, atol=1e-5)

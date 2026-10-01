import json

import numpy as np
import pytest

from helpers import JugadorAleatorio
from musarena.actions import Descarte, Envido, IllegalActionError, Mus, Ordago, Reenvido
from musarena.cards import Carta, Palo
from musarena.cli import main
from musarena.grabacion import (
    Grabador,
    PartidaGrabada,
    accion_a_dict,
    accion_desde_dict,
    cargar_partidas,
    estado_final,
    reproducir,
)
from musarena.match import Match
from musarena.players import crear_jugador


def _jugar_y_grabar(tmp_path, seed=5, tipos=("humano", "reglas", "random", "reglas")):
    mesa = [JugadorAleatorio(seed=seed * 4 + i) if t == "humano" else crear_jugador(t, seed=i)
            for i, t in enumerate(tipos)]
    grabador = Grabador(seed, 3, tipos)
    vistas = []

    def al_decidir(d):
        vistas.append(d)
        grabador(d)

    match = Match(mesa, seed=seed, al_decidir=al_decidir)
    match.play()
    return grabador.guardar(match, tmp_path), match, vistas


def test_las_acciones_se_guardan_y_se_recuperan_igual():
    descarte = Descarte(frozenset({Carta(12, Palo.OROS), Carta(3, Palo.BASTOS)}))
    for accion in (Mus(), descarte, Envido(), Envido(7), Reenvido(4), Ordago()):
        datos = json.loads(json.dumps(accion_a_dict(accion)))
        assert accion_desde_dict(datos) == accion
    with pytest.raises(ValueError):
        accion_desde_dict({"tipo": "Trampa"})


def test_una_partida_grabada_se_reproduce_exactamente(tmp_path):
    ruta, match, vistas = _jugar_y_grabar(tmp_path)
    partida = PartidaGrabada.cargar(ruta)
    assert partida.terminada and partida.ganador == match.ganador
    assert partida.jugadores == ["humano", "reglas", "random", "reglas"]
    repetidas = list(reproducir(partida))
    assert len(repetidas) == len(vistas)
    for original, repetida in zip(vistas, repetidas, strict=True):
        assert repetida.asiento == original.asiento and repetida.accion == original.accion
        assert repetida.observacion.cartas == original.observacion.cartas
        assert repetida.legales == original.legales
    final = estado_final(partida)
    assert final.vacas == match.state.vacas and final.ganador == match.ganador
    assert [p.seed for p in cargar_partidas(tmp_path)] == [5]


def test_una_partida_que_no_cuadra_se_detecta(tmp_path):
    ruta, _, _ = _jugar_y_grabar(tmp_path)
    partida = PartidaGrabada.cargar(ruta)
    partida.acciones[0] = (partida.acciones[0][0], {"tipo": "Quiero"})  # en el mus no se puede
    with pytest.raises(IllegalActionError):
        list(reproducir(partida))


def test_datos_de_entrenamiento_de_las_partidas_humanas(tmp_path):
    pytest.importorskip("torch")
    from musarena.ia import acciones
    from musarena.ia.codificacion import N_ENTRADAS
    from musarena.ia.entrenamiento.datos import de_partidas

    ruta, _, vistas = _jugar_y_grabar(tmp_path)
    d = de_partidas([PartidaGrabada.cargar(ruta)])
    n = len(d["y"])
    assert n == sum(v.asiento == 0 for v in vistas)  # solo las decisiones del humano
    assert d["x"].shape == (n, N_ENTRADAS) and d["mascara"].shape == (n, acciones.N_ACCIONES)
    assert d["mascara"][np.arange(n), d["y"]].all()
    assert set(np.unique(d["valor"])) <= {-1.0, 1.0}


def test_mus_play_graba_las_partidas_con_humanos(tmp_path, monkeypatch, capsys):
    respuestas = iter(["1"] * 100_000 + [""] * 10)  # el humano elige siempre la primera opción
    monkeypatch.setattr("builtins.input", lambda _="": next(respuestas))
    carpeta = tmp_path / "partidas"
    main(["--jugadores", "humano,random,random,random", "--mejor-de", "3", "--seed", "3",
          "--carpeta-partidas", str(carpeta)])
    assert "Partida guardada en" in capsys.readouterr().out
    (partida,) = cargar_partidas(carpeta)
    assert partida.seed == 3 and partida.terminada
    assert len(list(reproducir(partida))) == len(partida.acciones)
    main(["--jugadores", "random,random,random,random", "--mejor-de", "3", "--seed", "4",
          "--carpeta-partidas", str(tmp_path / "solo_bots")])
    assert not (tmp_path / "solo_bots").exists()  # sin humanos no se graba

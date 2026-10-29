"""Las partidas de la web se guardan en la base de datos y se exportan para entrenar."""

import json
import random

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from musarena.grabacion import PartidaGrabada, estado_final, reproducir  # noqa: E402
from musarena.web.app import crear_app  # noqa: E402
from musarena.web.archivo import exportar, main, partidas_guardadas  # noqa: E402
from musarena.web.bd import partidas_web  # noqa: E402
from musarena.web.config import Config  # noqa: E402
from musarena.web.mesas import GestorMesas  # noqa: E402


@pytest.fixture
def app(tmp_path):
    config = Config(pausa_bots=0, carpeta_partidas="", bd=f"sqlite:///{tmp_path / 'mus.db'}")
    return crear_app(config, GestorMesas(config))


def _mesa(cliente, asientos=("humano", "random", "humano", "random")):
    r = cliente.post("/api/mesas", json={"asientos": list(asientos),
                                         "nombres": ["Pablo", None, "Sara", None]})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["mesa"], {a["asiento"]: a["token"] for a in d["asientos"] if a["token"]}


def _jugar(cliente, mesa, tokens, rng, hasta_manos=None):
    """Los humanos juegan al azar hasta el final (o hasta ``hasta_manos`` manos)."""
    for _ in range(3000):
        t0 = next(iter(tokens.values()))
        v = cliente.get(f"/api/mesas/{mesa}", headers={"X-Token": t0}).json()
        if v["ganador"] is not None:
            return
        if hasta_manos is not None and len(v["manos_jugadas"]) >= hasta_manos:
            return
        token = tokens.get(v["turno"])
        if token is None:
            continue  # le toca a un bot: juega al volver a mirar
        v = cliente.get(f"/api/mesas/{mesa}", headers={"X-Token": token}).json()
        cliente.post(f"/api/mesas/{mesa}/jugar", headers={"X-Token": token},
                     json={"accion": rng.choice(v["acciones"])["id"], "version": v["version"]})
    raise AssertionError("La partida no ha terminado")


def _filas(app):
    with app.state.archivo.motor.connect() as c:
        return c.execute(select(partidas_web)).all()


def test_se_guarda_al_acabar_cada_mano_y_al_terminar(app):
    cliente = TestClient(app)
    mesa, tokens = _mesa(cliente)
    assert _filas(app) == []  # nada jugado, nada guardado
    _jugar(cliente, mesa, tokens, random.Random(1), hasta_manos=1)
    (fila,) = _filas(app)
    assert fila.mesa == mesa and not fila.terminada and fila.acciones
    _jugar(cliente, mesa, tokens, random.Random(2))
    (fila,) = _filas(app)
    assert fila.terminada and fila.ganador in (0, 1)
    assert fila.jugadores == ["humano", "random", "humano", "random"]
    # Sin nombres: solo el tipo de cada asiento.
    assert "Pablo" not in json.dumps([fila.jugadores, fila.acciones])
    # La partida guardada se repite exactamente.
    (_, partida), = partidas_guardadas(app.state.archivo.motor)
    final = estado_final(partida)
    assert final.terminada and final.ganador == fila.ganador
    assert sum(1 for _ in reproducir(partida)) == len(fila.acciones)


def test_una_mesa_que_se_cierra_a_medias_queda_guardada(app):
    cliente = TestClient(app)
    mesa, tokens = _mesa(cliente)
    _jugar(cliente, mesa, tokens, random.Random(3), hasta_manos=1)
    # Unas jugadas más, sin acabar la mano, y se cierra la mesa (por inactividad).
    app.state.mesas.obtener(mesa).cerrar()
    (fila,) = _filas(app)
    assert not fila.terminada and len(fila.acciones) == len(app.state.mesas.obtener(mesa).acciones)


def test_un_fallo_al_guardar_no_rompe_la_partida(app):
    cliente = TestClient(app)

    def roto(_):
        raise RuntimeError("la base de datos no responde")

    app.state.mesas.al_grabar = roto
    mesa, tokens = _mesa(cliente)
    _jugar(cliente, mesa, tokens, random.Random(4))
    assert app.state.mesas.obtener(mesa).match.terminada


def test_exportar_a_archivos(app, tmp_path):
    cliente = TestClient(app)
    for semilla in (5, 6):
        mesa, tokens = _mesa(cliente)
        _jugar(cliente, mesa, tokens, random.Random(semilla))
    carpeta = tmp_path / "exportadas"
    assert exportar(app.state.archivo.motor, carpeta) == 2
    archivos = sorted(carpeta.glob("web_*.json"))
    assert len(archivos) == 2
    for archivo in archivos:
        partida = PartidaGrabada.cargar(archivo)
        assert partida.terminada and estado_final(partida).terminada
    # Exportar otra vez no duplica nada.
    assert exportar(app.state.archivo.motor, carpeta) == 2
    assert len(list(carpeta.glob("*.json"))) == 2
    # Desde la terminal, con la URL de la base de datos.
    url = app.state.config.bd
    assert main([str(tmp_path / "otra"), "--bd", url]) == 0
    assert len(list((tmp_path / "otra").glob("*.json"))) == 2


def test_las_partidas_exportadas_sirven_para_entrenar(app, tmp_path):
    datos = pytest.importorskip("musarena.ia.entrenamiento.datos")
    cliente = TestClient(app)
    mesa, tokens = _mesa(cliente)
    _jugar(cliente, mesa, tokens, random.Random(7))
    (_, partida), = partidas_guardadas(app.state.archivo.motor)
    ejemplos = datos.de_partidas([partida])
    assert len(ejemplos["y"]) > 0  # decisiones de los dos humanos

import json
import threading
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from musarena.grabacion import cargar_partidas, reproducir  # noqa: E402
from musarena.web.app import crear_app  # noqa: E402
from musarena.web.config import Config  # noqa: E402
from musarena.web.mesas import GestorMesas  # noqa: E402
from musarena.web.torneos import GestorTorneos  # noqa: E402


class Reloj:
    """Reloj de mentira para controlar las pausas de los bots."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def entorno(tmp_path):
    config = Config(pausa_bots=0, carpeta_partidas=str(tmp_path / "partidas"),
                    procesos_torneo=1, max_mesas=5, minutos_inactiva=10,
                    max_partidas_torneo=20)
    reloj = Reloj()
    mesas = GestorMesas(config, reloj)
    app = crear_app(config, mesas, GestorTorneos(config))
    return TestClient(app), mesas, reloj, config


def _crear(cliente, asientos=("humano", "random", "random", "random"), mejor_de=3):
    r = cliente.post("/api/mesas", json={"asientos": list(asientos), "mejor_de": mejor_de})
    assert r.status_code == 200, r.text
    return r.json()


def _ver(cliente, mesa, token):
    return cliente.get(f"/api/mesas/{mesa}", headers={"X-Token": token})


# --- Opciones y páginas ---


def test_opciones_y_pagina(entorno):
    cliente, *_ = entorno
    tipos = [t["valor"] for t in cliente.get("/api/opciones").json()["tipos"]]
    assert {"humano", "inteligente", "reglas:agresivo", "bots/prudente.py"} <= set(tipos)
    r = cliente.get("/")
    assert r.status_code == 200 and "Mus Arena" in r.text
    assert r.headers["Referrer-Policy"] == "no-referrer"


def test_reglas_y_clasificacion(entorno):
    cliente, *_ = entorno
    assert "Reglas del mus" in cliente.get("/api/reglas").text
    assert cliente.get("/api/clasificacion").json()["clasificacion"][0]["puesto"] == 1


# --- Mesas ---


def test_solo_los_humanos_tienen_codigo(entorno):
    cliente, *_ = entorno
    datos = _crear(cliente, ("humano", "reglas", "humano", "inteligente"))
    tokens = [a["token"] for a in datos["asientos"]]
    assert tokens[0] and tokens[2] and tokens[1] is None and tokens[3] is None
    assert tokens[0] != tokens[2] and len(tokens[0]) >= 20


def test_sin_codigo_no_se_ve_nada(entorno):
    cliente, *_ = entorno
    datos = _crear(cliente)
    assert _ver(cliente, datos["mesa"], "").status_code == 403
    assert _ver(cliente, datos["mesa"], "inventado").status_code == 403
    assert _ver(cliente, "no-existe", datos["asientos"][0]["token"]).status_code == 404


def test_mesas_que_no_valen(entorno):
    cliente, *_ = entorno
    for asientos in (["random"] * 4, ["humano", "random", "random"],
                     ["humano", "random", "random", "../../secreto.py"],
                     ["humano", "random", "random", "inteligente:otro.npz"]):
        r = cliente.post("/api/mesas", json={"asientos": asientos})
        assert r.status_code in (400, 422), asientos
    r = cliente.post("/api/mesas", json={"asientos": ["humano"] + ["random"] * 3, "mejor_de": 4})
    assert r.status_code == 400


def test_partida_entera_por_la_api_sin_ver_cartas_ajenas(entorno):
    cliente, mesas, _, config = entorno
    datos = _crear(cliente, ("humano", "reglas", "random", "basico"))
    mesa_id, token = datos["mesa"], datos["asientos"][0]["token"]
    mesa = mesas.obtener(mesa_id)
    jugadas = 0
    while True:
        v = _ver(cliente, mesa_id, token).json()
        # Lo que manda el servidor no contiene ninguna carta que tengan ahora los demás
        # (las manos ya terminadas sí, porque al final de cada mano se enseñan).
        sin_resumenes = json.dumps({k: x for k, x in v.items() if k != "manos_jugadas"})
        for asiento in (1, 2, 3):
            for c in mesa.match.state.cartas[asiento]:
                assert f'"{c.numero}-{c.palo.value}"' not in sin_resumenes
        assert len(v["cartas"]) == 4
        if v["ganador"] is not None:
            break
        assert v["es_mi_turno"]  # sin pausa, los bots juegan hasta que le toca al humano
        r = cliente.post(f"/api/mesas/{mesa_id}/jugar", headers={"X-Token": token},
                         json={"accion": 0, "version": v["version"]})
        assert r.status_code == 200, r.text
        jugadas += 1
        assert jugadas < 5000
    # La partida queda grabada y se puede reproducir entera.
    (partida,) = cargar_partidas(config.carpeta_partidas)
    assert partida.terminada and partida.jugadores[0] == "humano"
    assert len(list(reproducir(partida))) == len(partida.acciones)


def test_jugadas_rechazadas(entorno):
    cliente, *_ = entorno
    datos = _crear(cliente, ("humano", "random", "humano", "random"))
    mesa_id = datos["mesa"]
    t0, t2 = datos["asientos"][0]["token"], datos["asientos"][2]["token"]
    v = _ver(cliente, mesa_id, t0).json()
    a_quien = v["turno"]
    token_turno, token_otro = (t0, t2) if a_quien == 0 else (t2, t0)
    version = _ver(cliente, mesa_id, token_turno).json()["version"]
    jugar = lambda token, accion, version: cliente.post(  # noqa: E731
        f"/api/mesas/{mesa_id}/jugar", headers={"X-Token": token},
        json={"accion": accion, "version": version})
    if a_quien in (0, 2):
        assert jugar(token_otro, 0, version).status_code == 409  # no es su turno
        assert jugar(token_turno, 99, version).status_code == 400  # no existe esa jugada
        assert jugar(token_turno, 0, version + 7).status_code == 409  # versión vieja
        assert jugar(token_turno, 0, version).status_code == 200
        assert jugar(token_turno, 0, version).status_code == 409  # el doble clic no cuenta
    assert jugar("", 0, version).status_code == 403


def test_los_bots_esperan_su_pausa(tmp_path):
    config = Config(pausa_bots=1.0, carpeta_partidas="")
    reloj = Reloj()
    mesas = GestorMesas(config, reloj)
    mesa = mesas.crear(["humano", "random", "random", "random"])
    token = mesa.tokens[0]
    while mesa.match.state.turno == 0:  # que le toque a un bot
        v = mesa.vista(token)
        mesa.jugar(token, 0, v["version"])
    version = mesa.vista(token)["version"]
    assert mesa.vista(token)["version"] == version  # sin pasar el tiempo, no juega
    reloj.t += 1.0
    assert mesa.vista(token)["version"] == version + 1  # una jugada por pausa


def test_chat(entorno):
    cliente, *_ = entorno
    datos = _crear(cliente, ("humano", "random", "humano", "random"))
    mesa_id = datos["mesa"]
    t0, t2 = datos["asientos"][0]["token"], datos["asientos"][2]["token"]
    texto = "<script>alert(1)</script> ¡vaya mano!"
    r = cliente.post(f"/api/mesas/{mesa_id}/chat", headers={"X-Token": t0}, json={"texto": texto})
    assert r.status_code == 200
    (mensaje,) = _ver(cliente, mesa_id, t2).json()["chat"]
    assert mensaje["quien"] == "Jugador 1"
    assert mensaje["texto"].startswith("<script>")  # tal cual: la página lo pinta como texto
    largo = cliente.post(f"/api/mesas/{mesa_id}/chat", headers={"X-Token": t0},
                         json={"texto": "x" * 900})
    assert len(largo.json()["chat"][-1]["texto"]) <= 200


def test_limite_de_mesas_y_caducidad(entorno):
    cliente, mesas, reloj, _ = entorno
    for _ in range(5):
        _crear(cliente)
    r = cliente.post("/api/mesas", json={"asientos": ["humano"] + ["random"] * 3})
    assert r.status_code == 503
    reloj.t += 11 * 60  # más de 10 minutos sin actividad: se cierran
    _crear(cliente)
    assert len(mesas) == 1


# --- Torneos ---


def _esperar(cliente, torneo_id, segundos=60):
    limite = time.time() + segundos
    while time.time() < limite:
        estado = cliente.get(f"/api/torneos/{torneo_id}").json()
        if estado["estado"] != "jugando":
            return estado
        time.sleep(0.05)
    raise AssertionError("El torneo no ha terminado")


def test_torneo_desde_la_web(entorno):
    cliente, *_ = entorno
    lista = cliente.get("/api/torneos/participantes").json()["participantes"]
    posibles = [p["valor"] for p in lista]
    assert "humano" not in posibles and "inteligente" in posibles
    participantes = ["random", "basico", "bots/prudente.py"]
    r = cliente.post("/api/torneos", json={"participantes": participantes, "partidas": 4})
    assert r.status_code == 200, r.text
    estado = _esperar(cliente, r.json()["id"])
    assert estado["estado"] == "terminado" and estado["progreso"] == 1
    tabla = estado["resultado"]["clasificacion"]
    assert [f["puesto"] for f in tabla] == [1, 2, 3]
    assert len(estado["resultado"]["cruces"]) == 3


def test_torneos_que_no_valen(entorno):
    cliente, *_ = entorno
    for datos in ({"participantes": ["random"], "partidas": 4},
                  {"participantes": ["random", "humano"], "partidas": 4},
                  {"participantes": ["random", "../otro.py"], "partidas": 4},
                  {"participantes": ["random", "basico"], "partidas": 21}):  # más del máximo
        assert cliente.post("/api/torneos", json=datos).status_code in (400, 422), datos


def test_solo_un_torneo_a_la_vez():
    config = Config(max_partidas_torneo=20)
    soltar = threading.Event()

    class Falso:
        def a_dict(self):
            return {"clasificacion": [], "cruces": []}

    def jugar_lento(*args, al_progreso=None, **kwargs):
        al_progreso(1, 2)
        soltar.wait(5)
        return Falso()

    torneos = GestorTorneos(config, jugar=jugar_lento)
    primero = torneos.lanzar(["random", "basico"], 4)
    with pytest.raises(Exception, match="Ya hay un torneo"):
        torneos.lanzar(["random", "basico"], 4)
    soltar.set()
    for _ in range(100):
        if primero.estado != "jugando":
            break
        time.sleep(0.02)
    assert primero.estado == "terminado"
    assert torneos.lanzar(["random", "basico"], 4).estado in ("jugando", "terminado")

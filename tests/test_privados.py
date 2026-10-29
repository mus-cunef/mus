"""Cuentas y torneos privados, por la API (como lo haría la página)."""

import random

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from musarena.web.app import crear_app  # noqa: E402
from musarena.web.bd import usuarios  # noqa: E402
from musarena.web.config import Config  # noqa: E402
from musarena.web.mesas import GestorMesas  # noqa: E402

DIA = 24 * 3600
CLAVE = "clave-secreta-1"


class Reloj:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def app(reloj, tmp_path):
    config = Config(pausa_bots=0, carpeta_partidas="", bd=f"sqlite:///{tmp_path / 'mus.db'}")
    return crear_app(config, GestorMesas(config), reloj=reloj)


def _cliente(app) -> TestClient:
    return TestClient(app, headers={"X-Mus": "1"})


def _usuario(app, nombre: str) -> TestClient:
    c = _cliente(app)
    r = c.post("/api/cuenta/registro", json={"nombre": nombre, "clave": CLAVE})
    assert r.status_code == 200, r.text
    return c


def _torneo(organizador, reloj, **formato) -> str:
    r = organizador.post("/api/privados", json={
        "nombre": "Torneo de la peña", "formato": {"max_parejas": 16, **formato},
        "fecha_limite": reloj.t + 7 * DIA})
    assert r.status_code == 200, r.text
    return r.json()["codigo"]


def _inscribir(app, codigo: str, n: int, prefijo: str = "j") -> list[tuple]:
    """Inscribe ``n`` parejas confirmadas. Devuelve (cliente1, cliente2, id) de cada una."""
    salida = []
    for i in range(n):
        a, b = _usuario(app, f"{prefijo}{i}a"), _usuario(app, f"{prefijo}{i}b")
        r = a.post(f"/api/privados/{codigo}/parejas",
                   json={"nombre": f"Pareja {prefijo}{i}", "companero": f"{prefijo}{i}b"})
        assert r.status_code == 200, r.text
        pid = r.json()["yo"]["pareja"]
        assert b.post(f"/api/privados/{codigo}/parejas/{pid}/aceptar").status_code == 200
        salida.append((a, b, pid))
    return salida


def _ver(cliente, codigo):
    r = cliente.get(f"/api/privados/{codigo}")
    assert r.status_code == 200, r.text
    return r.json()


def _empezar(codigo: str, partido: dict, clientes) -> None:
    """Los cuatro jugadores le dan a "Empezar"."""
    for cliente in clientes:
        r = cliente.post(f"/api/privados/{codigo}/partidos/{partido['id']}/listo", json={})
        assert r.status_code == 200, r.text


def _jugar_partido(codigo: str, partido: dict, de_pareja: dict, rng: random.Random) -> None:
    """Los cuatro jugadores juegan el partido entero, cada uno desde su sesión."""
    mesas = {}
    _empezar(codigo, partido, [c for pareja in (partido["a"], partido["b"])
                               for c in de_pareja[pareja][:2]])
    for pareja in (partido["a"], partido["b"]):
        for cliente in de_pareja[pareja][:2]:
            r = cliente.post(f"/api/privados/{codigo}/partidos/{partido['id']}/entrar")
            assert r.status_code == 200, r.text
            d = r.json()
            mesas[d["asiento"]] = (cliente, d["mesa"], d["token"])
    assert sorted(mesas) == [0, 1, 2, 3]
    assert len({m for _, m, _ in mesas.values()}) == 1  # los cuatro en la misma mesa
    for _ in range(5000):
        cliente, mesa, token = mesas[0]
        v = cliente.get(f"/api/mesas/{mesa}", headers={"X-Token": token}).json()
        if v["ganador"] is not None:
            return
        cliente, mesa, token = mesas[v["turno"]]
        v = cliente.get(f"/api/mesas/{mesa}", headers={"X-Token": token}).json()
        accion = rng.choice(v["acciones"])
        r = cliente.post(f"/api/mesas/{mesa}/jugar", headers={"X-Token": token},
                         json={"accion": accion["id"], "version": v["version"]})
        assert r.status_code == 200, r.text
    raise AssertionError("El partido no ha terminado")


# --- Cuentas ---


def test_registro_entrada_y_salida(app):
    c = _cliente(app)
    assert c.get("/api/cuenta").json() == {"usuario": None}
    r = c.post("/api/cuenta/registro", json={"nombre": "Pablo", "clave": CLAVE})
    assert r.json() == {"usuario": {"nombre": "Pablo"}}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert c.get("/api/cuenta").json()["usuario"]["nombre"] == "Pablo"
    c.post("/api/cuenta/salir")
    assert c.get("/api/cuenta").json() == {"usuario": None}
    otro = _cliente(app)
    r = otro.post("/api/cuenta/entrar", json={"nombre": "pablo", "clave": CLAVE})
    assert r.status_code == 200  # sin distinguir mayúsculas
    assert otro.post("/api/cuenta/entrar", json={"nombre": "Pablo", "clave": "mala-clave"}
                     ).status_code == 401
    assert otro.post("/api/cuenta/entrar", json={"nombre": "nadie", "clave": CLAVE}
                     ).status_code == 401


def test_las_contrasenas_no_se_guardan(app):
    _usuario(app, "Sara")
    with app.state.cuentas.motor.connect() as c:
        guardada = c.execute(select(usuarios.c.clave)).scalar_one()
    assert CLAVE not in guardada and guardada.startswith("scrypt$")


@pytest.mark.parametrize(("nombre", "clave"), [
    ("ab", CLAVE), ("x" * 21, CLAVE), ("con espacio", CLAVE), ("<script>", CLAVE),
    ("Ines", "corta"), ("Ines", "Ines"),
])
def test_registro_rechaza_datos_malos(app, nombre, clave):
    r = _cliente(app).post("/api/cuenta/registro", json={"nombre": nombre, "clave": clave})
    assert r.status_code == 400


def test_nombres_unicos_sin_distinguir_mayusculas(app):
    _usuario(app, "Ines")
    r = _cliente(app).post("/api/cuenta/registro", json={"nombre": "INES", "clave": CLAVE})
    assert r.status_code == 409


def test_bloqueo_tras_muchos_fallos(app, reloj):
    _usuario(app, "Pablo")
    c = _cliente(app)
    for _ in range(8):
        assert c.post("/api/cuenta/entrar", json={"nombre": "Pablo", "clave": "xxxxxxxx"}
                      ).status_code == 401
    # Bloqueado incluso con la contraseña buena…
    assert c.post("/api/cuenta/entrar", json={"nombre": "Pablo", "clave": CLAVE}
                  ).status_code == 429
    reloj.t += 16 * 60  # …hasta que pasa el bloqueo
    assert c.post("/api/cuenta/entrar", json={"nombre": "Pablo", "clave": CLAVE}
                  ).status_code == 200


def test_sin_la_cabecera_x_mus_no_se_cambia_nada(app):
    """Defensa contra CSRF: otra web no puede poner cabeceras propias en una petición."""
    c = TestClient(app)
    r = c.post("/api/cuenta/registro", json={"nombre": "Pablo", "clave": CLAVE})
    assert r.status_code == 403


# --- Crear e inscribirse ---


def test_sin_sesion_no_se_ve_ni_se_crea_nada(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj)
    anonimo = _cliente(app)
    assert anonimo.get(f"/api/privados/{codigo}").status_code == 401
    assert anonimo.post("/api/privados", json={"nombre": "x", "formato": {},
                                               "fecha_limite": reloj.t + DIA}).status_code == 401
    assert org.get("/api/privados/codigo-que-no-existe").status_code == 404


def test_crear_valida_formato_y_fecha(app, reloj):
    org = _usuario(app, "Pablo")
    malo = org.post("/api/privados", json={"nombre": "x", "formato": {"tipo": "copa"},
                                           "fecha_limite": reloj.t + DIA})
    assert malo.status_code == 400
    pasada = org.post("/api/privados", json={"nombre": "x", "formato": {},
                                             "fecha_limite": reloj.t - 1})
    assert pasada.status_code == 400
    previa = org.post("/api/privados/vista-previa", json={"formato": {"max_parejas": 32}})
    assert "8 grupos de 4" in previa.json()["descripcion"]


def test_inscripcion_por_parejas(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj, max_parejas=2)
    a, b, c = _usuario(app, "Ana"), _usuario(app, "Berta"), _usuario(app, "Carla")
    # Compañero que no existe, o uno mismo.
    assert a.post(f"/api/privados/{codigo}/parejas",
                  json={"nombre": "Las A", "companero": "nadie"}).status_code == 404
    assert a.post(f"/api/privados/{codigo}/parejas",
                  json={"nombre": "Las A", "companero": "Ana"}).status_code == 400
    v = a.post(f"/api/privados/{codigo}/parejas",
               json={"nombre": "Las A", "companero": "berta"}).json()
    pid = v["yo"]["pareja"]
    # Pendiente: la ven sus jugadores y el organizador, pero no los demás.
    assert [p["confirmada"] for p in v["parejas"]] == [False]
    assert _ver(c, codigo)["parejas"] == []
    assert _ver(b, codigo)["parejas"][0]["invitado_yo"] is True
    # Nadie puede estar en dos parejas, ni repetir nombre.
    assert b.post(f"/api/privados/{codigo}/parejas",
                  json={"nombre": "Otra", "companero": "Carla"}).status_code == 409
    assert c.post(f"/api/privados/{codigo}/parejas",
                  json={"nombre": "las a", "companero": "Pablo"}).status_code == 409
    # Solo el invitado puede aceptar.
    assert c.post(f"/api/privados/{codigo}/parejas/{pid}/aceptar").status_code == 404
    assert b.post(f"/api/privados/{codigo}/parejas/{pid}/aceptar").status_code == 200
    assert _ver(c, codigo)["parejas"][0]["jugadores"] == ["Ana", "Berta"]
    # Rechazar una invitación la borra.
    v = c.post(f"/api/privados/{codigo}/parejas",
               json={"nombre": "Las C", "companero": "Pablo"}).json()
    otra = v["yo"]["pareja"]
    assert org.post(f"/api/privados/{codigo}/parejas/{otra}/retirar").status_code == 200
    assert _ver(c, codigo)["yo"]["pareja"] is None


def test_torneo_completo_y_fecha_limite(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj, max_parejas=2)
    _inscribir(app, codigo, 2)
    x = _usuario(app, "Xavi")
    _usuario(app, "Yago")
    r = x.post(f"/api/privados/{codigo}/parejas", json={"nombre": "Tarde", "companero": "Yago"})
    assert r.status_code == 409  # completo
    # Al pasar la fecha límite se sortea solo.
    reloj.t += 8 * DIA
    v = _ver(org, codigo)
    assert v["estado"] == "en_curso" and len(v["partidos"]) == 1
    assert v["cuadro"]["rondas"][0]["nombre"] == "Final"


def test_solo_el_organizador_empieza_y_hacen_falta_dos_parejas(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj)
    parejas = _inscribir(app, codigo, 1)
    assert org.post(f"/api/privados/{codigo}/empezar").status_code == 409
    _inscribir(app, codigo, 1, prefijo="k")
    assert parejas[0][0].post(f"/api/privados/{codigo}/empezar").status_code == 403
    assert org.post(f"/api/privados/{codigo}/empezar").status_code == 200
    assert _ver(org, codigo)["estado"] == "en_curso"


# --- Jugar ---


def test_cuatro_parejas_semis_y_final_jugadas_de_verdad(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj, tercer_puesto=True)
    inscritas = _inscribir(app, codigo, 4)
    de_pareja = {pid: (a, b) for a, b, pid in inscritas}
    org.post(f"/api/privados/{codigo}/empezar")
    v = _ver(org, codigo)
    assert [r["nombre"] for r in v["cuadro"]["rondas"]] == ["Semifinales", "Final"]
    rng = random.Random(3)
    # Semifinales y tercer puesto: el organizador da una por ganada; las demás se juegan.
    semis = [p for p in v["partidos"] if p["fase"] == "cuadro" and p["ronda"] == 0]
    _jugar_partido(codigo, semis[0], de_pareja, rng)
    r = org.post(f"/api/privados/{codigo}/partidos/{semis[1]['id']}/ganador",
                 json={"pareja": semis[1]["b"]})
    assert r.status_code == 200
    v = _ver(org, codigo)
    final = next(p for p in v["partidos"] if p["fase"] == "cuadro" and p["ronda"] == 1)
    tercero = next(p for p in v["partidos"] if p["fase"] == "tercero")
    assert final["estado"] == tercero["estado"] == "listo"
    jugada = next(p for p in v["partidos"] if p["id"] == semis[0]["id"])
    assert jugada["estado"] == "terminado" and not jugada["pase"]
    assert max(jugada["vacas"]) == 2 and final["a"] == jugada["ganador"]
    assert final["b"] == semis[1]["b"]
    _jugar_partido(codigo, final, de_pareja, rng)
    v = _ver(org, codigo)
    assert v["estado"] == "en_curso"  # falta el tercer puesto
    org.post(f"/api/privados/{codigo}/partidos/{tercero['id']}/ganador",
             json={"pareja": tercero["a"]})
    v = _ver(org, codigo)
    final = next(p for p in v["partidos"] if p["id"] == final["id"])
    assert v["estado"] == "terminado" and v["campeon"] == final["ganador"]
    # Estadísticas: los dos partidos jugados cuentan tantos, manos, envites…
    e = {x["pareja"]: x for x in v["estadisticas"]}
    campeon = e[v["campeon"]]
    assert campeon["jugados"] == 2 and campeon["ganados"] == 2
    assert campeon["tantos"][0] > 0 and campeon["manos"] > 0
    assert sum(x["jugados"] for x in e.values()) == 8


def test_solo_juegan_los_del_partido_y_cada_uno_en_su_asiento(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj)
    inscritas = _inscribir(app, codigo, 2)
    org.post(f"/api/privados/{codigo}/empezar")
    partido = _ver(org, codigo)["partidos"][0]
    assert org.post(f"/api/privados/{codigo}/partidos/{partido['id']}/entrar").status_code == 403
    assert org.post(f"/api/privados/{codigo}/partidos/{partido['id']}/listo",
                    json={}).status_code == 403
    _empezar(codigo, partido, [c for a, b, _ in inscritas for c in (a, b)])
    asientos = {}
    for a, b, _ in inscritas:
        for cliente in (a, b):
            d = cliente.post(f"/api/privados/{codigo}/partidos/{partido['id']}/entrar").json()
            asientos[d["asiento"]] = d["token"]
    assert len(set(asientos.values())) == 4  # un código distinto por asiento
    # La pareja A (la primera del partido) se sienta en los asientos 0 y 2.
    a_es = next(p for p in inscritas if p[2] == partido["a"])
    assert a_es[0].post(f"/api/privados/{codigo}/partidos/{partido['id']}/entrar"
                        ).json()["asiento"] in (0, 2)


def test_la_mesa_se_reconstruye_tras_un_reinicio(app, reloj, tmp_path):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj)
    inscritas = _inscribir(app, codigo, 2)
    org.post(f"/api/privados/{codigo}/empezar")
    partido = _ver(org, codigo)["partidos"][0]
    a = inscritas[0][0]
    _empezar(codigo, partido, [c for x, y, _ in inscritas for c in (x, y)])
    d = a.post(f"/api/privados/{codigo}/partidos/{partido['id']}/entrar").json()
    # Se juegan unas cuantas jugadas.
    jugadores = {}
    for x, y, _ in inscritas:
        for cliente in (x, y):
            e = cliente.post(f"/api/privados/{codigo}/partidos/{partido['id']}/entrar").json()
            jugadores[e["asiento"]] = (cliente, e["token"])
    for _ in range(12):
        cliente, token = jugadores[0]
        v = cliente.get(f"/api/mesas/{d['mesa']}", headers={"X-Token": token}).json()
        cliente, token = jugadores[v["turno"]]
        v = cliente.get(f"/api/mesas/{d['mesa']}", headers={"X-Token": token}).json()
        cliente.post(f"/api/mesas/{d['mesa']}/jugar", headers={"X-Token": token},
                     json={"accion": v["acciones"][-1]["id"], "version": v["version"]})
    antes = a.get(f"/api/mesas/{d['mesa']}", headers={"X-Token": d["token"]}).json()
    # "Reinicio": una aplicación nueva, sin nada en memoria, con la misma base de datos.
    config = app.state.config
    nueva = crear_app(config, GestorMesas(config), reloj=reloj)
    a2 = _cliente(nueva)
    a2.post("/api/cuenta/entrar", json={"nombre": "j0a", "clave": CLAVE})
    despues = a2.get(f"/api/mesas/{d['mesa']}", headers={"X-Token": d["token"]}).json()
    assert despues["version"] == antes["version"] == 12
    assert despues["cartas"] == antes["cartas"] and despues["tantos"] == antes["tantos"]
    assert despues["historial"] == antes["historial"]


def test_grupos_con_17_parejas_y_cuadro_con_pases(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj, max_parejas=20)
    _inscribir(app, codigo, 17)
    org.post(f"/api/privados/{codigo}/empezar")
    v = _ver(org, codigo)
    assert v["resuelto"]["tipo"] == "grupos"
    assert sorted(len(g["tabla"]) for g in v["grupos"]) == [3, 3, 3, 4, 4]
    assert v["cuadro"] is None
    # El organizador resuelve todos los partidos de grupos: gana siempre la pareja "a".
    for p in v["partidos"]:
        r = org.post(f"/api/privados/{codigo}/partidos/{p['id']}/ganador", json={"pareja": p["a"]})
        assert r.status_code == 200
    v = _ver(org, codigo)
    # Pasan 2 de cada grupo: 10 parejas -> cuadro de 16 con 6 pases directos.
    assert [r["nombre"] for r in v["cuadro"]["rondas"]][0] == "Octavos de final"
    primera = [p for p in v["partidos"] if p["fase"] == "cuadro" and p["ronda"] == 0]
    assert sum(p["pase"] for p in primera) == 6
    grupo_de = {p["id"]: p["grupo"] for p in v["parejas"]}
    clasificados = {g["tabla"][i]["pareja"] for g in v["grupos"] for i in range(2)}
    en_cuadro = {x for p in primera for x in (p["a"], p["b"]) if x is not None}
    assert en_cuadro == clasificados
    for p in primera:  # ningún cruce entre parejas del mismo grupo en la primera ronda
        if p["a"] and p["b"]:
            assert grupo_de[p["a"]] != grupo_de[p["b"]]
    # Los ganadores de los pases ya esperan en la segunda ronda.
    segunda = [p for p in v["partidos"] if p["fase"] == "cuadro" and p["ronda"] == 1]
    assert sum(x is not None for p in segunda for x in (p["a"], p["b"])) == 6


def test_liga(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj, tipo="liga")
    _inscribir(app, codigo, 3)
    org.post(f"/api/privados/{codigo}/empezar")
    v = _ver(org, codigo)
    assert len(v["partidos"]) == 3 and v["cuadro"] is None
    for p in v["partidos"]:
        org.post(f"/api/privados/{codigo}/partidos/{p['id']}/ganador", json={"pareja": p["a"]})
    v = _ver(org, codigo)
    assert v["estado"] == "terminado" and v["campeon"] == v["liga"][0]["pareja"]


def test_mis_torneos_y_cancelar(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj)
    (a, _, _), *_ = _inscribir(app, codigo, 2)
    assert [t["codigo"] for t in a.get("/api/privados").json()["torneos"]] == [codigo]
    lista = org.get("/api/privados").json()["torneos"]
    assert lista[0]["organizo"] is True and lista[0]["parejas"] == 2
    assert a.post(f"/api/privados/{codigo}/cancelar").status_code == 403
    assert org.post(f"/api/privados/{codigo}/cancelar").status_code == 200
    assert _ver(a, codigo)["estado"] == "cancelado"


def test_la_partida_empieza_cuando_los_cuatro_le_dan_a_empezar(app, reloj):
    org = _usuario(app, "Pablo")
    codigo = _torneo(org, reloj)
    inscritas = _inscribir(app, codigo, 2)
    org.post(f"/api/privados/{codigo}/empezar")
    partido = _ver(org, codigo)["partidos"][0]
    ruta = f"/api/privados/{codigo}/partidos/{partido['id']}"
    a_es = next(p for p in inscritas if p[2] == partido["a"])
    b_es = next(p for p in inscritas if p[2] == partido["b"])
    orden = [a_es[0], b_es[0], a_es[1], b_es[1]]  # el orden de los asientos
    nombres = ["j0a", "j1a", "j0b", "j1b"] if a_es[2] == inscritas[0][2] else \
        ["j1a", "j0a", "j1b", "j0b"]
    # Antes de que le den los cuatro no hay mesa.
    assert orden[0].post(f"{ruta}/entrar").status_code == 409
    for i, cliente in enumerate(orden[:3]):
        v = cliente.post(f"{ruta}/listo", json={}).json()
        p = next(x for x in v["partidos"] if x["id"] == partido["id"])
        assert p["estado"] == "listo" and p["estoy_listo"] is True
        assert set(p["listos"]) == set(nombres[: i + 1])
        assert set(p["faltan"]) == set(nombres[i + 1:])
        assert cliente.post(f"{ruta}/entrar").status_code == 409
    # Uno se echa atrás y vuelve: sigue faltando el cuarto.
    v = orden[1].post(f"{ruta}/listo", json={"listo": False}).json()
    faltan = next(x for x in v["partidos"] if x["id"] == partido["id"])["faltan"]
    assert set(faltan) == {nombres[1], nombres[3]}
    orden[1].post(f"{ruta}/listo", json={})
    # El último en darle: empieza.
    v = orden[3].post(f"{ruta}/listo", json={}).json()
    assert next(x for x in v["partidos"] if x["id"] == partido["id"])["estado"] == "jugando"
    mesas = {c.post(f"{ruta}/entrar").json()["mesa"] for c in orden}
    assert len(mesas) == 1
    # Darle otra vez con la partida empezada no hace nada.
    assert orden[0].post(f"{ruta}/listo", json={}).status_code == 200


def test_una_base_de_datos_antigua_recibe_las_columnas_nuevas(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from musarena.web.bd import conectar

    url = f"sqlite:///{tmp_path / 'vieja.db'}"
    vieja = create_engine(url)
    with vieja.begin() as c:
        c.execute(text("CREATE TABLE partidos (id INTEGER PRIMARY KEY, torneo INTEGER, "
                       "fase VARCHAR(10), mejor_de INTEGER, estado VARCHAR(10))"))
        c.execute(text("INSERT INTO partidos VALUES (1, 1, 'liga', 3, 'listo')"))
    vieja.dispose()
    motor = conectar(url)
    columnas = {c["name"] for c in inspect(motor).get_columns("partidos")}
    assert {"listos", "acciones", "tokens"} <= columnas
    with motor.connect() as c:
        assert c.execute(text("SELECT estado FROM partidos")).scalar_one() == "listo"

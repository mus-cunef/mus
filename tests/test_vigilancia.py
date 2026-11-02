"""Un bot que falla, se cuelga o juega ilegal pierde la partida, pero no rompe el torneo.

Cada bot vigilado juega en otro proceso, así que las fábricas de los tests están a nivel de
módulo (``partial(_crear, Clase)``): tienen que poder enviarse a ese proceso.
"""

import multiprocessing
import os
import threading
import time
from functools import partial

import pytest

from musarena.actions import Envido, IllegalActionError, Quiero
from musarena.arena import enfrentar
from musarena.match import Match
from musarena.player import Bot
from musarena.players.random_bot import RandomBot
from musarena.torneo import jugar_torneo
from musarena.vigilancia import Caja, JugadorVigilado, cerrar_cajas


class Explota(Bot):
    def choose_action(self, observation, legal_actions):
        raise RuntimeError("¡bum!")


class Ilegal(Bot):
    def choose_action(self, observation, legal_actions):
        return Quiero()  # casi nunca es legal


class Colgado(Bot):
    def choose_action(self, observation, legal_actions):
        time.sleep(30)  # el vigilante no espera tanto


class NoSeCrea(Bot):
    def __init__(self, nombre=None, seed=None):
        raise ValueError("no arranco")

    def choose_action(self, observation, legal_actions):
        return legal_actions[0]


class Flotante(Bot):
    """Devuelve ``Envido(2.0)``: es igual a ``Envido(2)``, pero con un número de otro tipo."""

    def choose_action(self, observation, legal_actions):
        if Envido(2) in legal_actions:
            return Envido(2.0)
        return legal_actions[0]


class CambiaLasLegales(Bot):
    """Añade su jugada a la lista de legales que recibe y luego la devuelve."""

    def choose_action(self, observation, legal_actions):
        legal_actions.append(Quiero())
        return Quiero()


class Raro:
    def __eq__(self, otro):
        raise RuntimeError("no me compares")

    __hash__ = None

    def __repr__(self):
        raise RuntimeError("no me escribas")


class DevuelveRaro(Bot):
    def choose_action(self, observation, legal_actions):
        return Raro()


class SeSale(Bot):
    def __init__(self, nombre=None, seed=None):
        raise SystemExit(3)

    def choose_action(self, observation, legal_actions):
        return legal_actions[0]


class SeMata(Bot):
    def choose_action(self, observation, legal_actions):
        os._exit(1)  # mata su propio proceso


class NoSeSienta(Bot):
    def sit(self, asiento, chat):
        raise RuntimeError("esta silla no me gusta")

    def choose_action(self, observation, legal_actions):
        return legal_actions[0]


class Hablador(Bot):
    def choose_action(self, observation, legal_actions):
        self.say(f"juego {legal_actions[0]}")
        return legal_actions[0]


def _crear(clase, seed):
    return clase(seed=seed)


def _fabrica(clase):
    return partial(_crear, clase)


@pytest.mark.parametrize(("clase", "motivo"), [
    (Explota, "RuntimeError"), (Ilegal, "ilegal"), (Colgado, "no ha respondido"),
    (NoSeCrea, "al crear"), (CambiaLasLegales, "ilegal"), (DevuelveRaro, "Raro sin repr"),
    (SeSale, "SystemExit"), (SeMata, "su proceso ha terminado"), (NoSeSienta, "silla"),
])
def test_cada_falta_pierde_la_partida(clase, motivo):
    r = enfrentar(_fabrica(clase), "random", partidas=4, seed=1, vigilar=True,
                  limite_segundos=0.2)
    assert r.victorias_a == 0 and r.faltas_a == 4 and r.faltas_b == 0
    assert any(motivo in m for m in r.motivos_a), r.motivos_a
    assert "faltas" in str(r)


def test_sin_vigilancia_la_jugada_ilegal_sigue_parando_la_partida():
    with pytest.raises(IllegalActionError):
        enfrentar(_fabrica(Ilegal), "random", partidas=2, seed=1)


def test_la_vigilancia_no_cambia_nada_a_los_bots_que_juegan_bien():
    con = enfrentar("basico", "random", partidas=10, seed=3, vigilar=True)
    sin = enfrentar("basico", "random", partidas=10, seed=3)
    resumen = lambda r: (r.victorias_a, r.vacas_a, r.vacas_b)  # noqa: E731
    assert resumen(con) == resumen(sin)
    assert con.faltas_a == con.faltas_b == 0


def test_el_torneo_sigue_con_bots_rotos(tmp_path):
    (tmp_path / "explota.py").write_text(
        "from musarena.player import Bot\n\n"
        "class Explota(Bot):\n"
        "    tipo = 'explota'\n\n"
        "    def choose_action(self, observation, legal_actions):\n"
        "        raise RuntimeError('fallo a propósito')\n", encoding="utf-8")
    (tmp_path / "sintaxis.py").write_text("esto no es python (\n", encoding="utf-8")
    (tmp_path / "ilegal.py").write_text(
        "from musarena.actions import Quiero\nfrom musarena.player import Bot\n\n"
        "class Ilegal(Bot):\n"
        "    def choose_action(self, observation, legal_actions):\n"
        "        return Quiero()\n", encoding="utf-8")
    rotos = [str(tmp_path / n) for n in ("explota.py", "sintaxis.py", "ilegal.py")]
    r = jugar_torneo(["random", "basico", *rotos], partidas_por_cruce=4, seed=2, procesos=1,
                     limite_segundos=1.0)
    tabla = {f.nombre: f for f in r.tabla()}
    assert set(tabla) == {"random", "basico", "explota", "sintaxis", "ilegal"}
    for roto, ruta in zip(("explota", "sintaxis", "ilegal"), rotos, strict=True):
        assert tabla[roto].faltas > 0
        # Contra los que juegan bien no ganan nada (entre dos rotos, pierde el que falla antes).
        assert r.victorias(ruta, "random")[0] == r.victorias(ruta, "basico")[0] == 0
    assert tabla["random"].faltas == tabla["basico"].faltas == 0
    assert tabla["basico"].puesto <= 2  # los que juegan bien quedan arriba
    md = r.a_markdown()
    assert "## Faltas" in md and "fallo a propósito" in md
    assert any(i["nombre"] == "sintaxis" for i in r.a_dict()["incidencias"])


def test_una_jugada_igual_con_otro_tipo_cuenta_como_la_legal():
    # Envido(2.0) == Envido(2): se juega Envido(2), sin faltas y sin romper la partida.
    con = enfrentar(_fabrica(Flotante), "random", partidas=4, seed=1, vigilar=True)
    assert con.faltas_a == con.faltas_b == 0
    sin = enfrentar(_fabrica(Flotante), "random", partidas=4, seed=1)
    assert (sin.victorias_a, sin.vacas_a) == (con.victorias_a, con.vacas_a)


def test_la_partida_guarda_la_accion_legal_y_no_la_del_bot():
    decisiones = []
    jugadores = [Flotante(seed=0), RandomBot(seed=1), Flotante(seed=2), RandomBot(seed=3)]
    Match(jugadores, seed=4, al_decidir=decisiones.append).play()
    envites = [d.accion for d in decisiones if isinstance(d.accion, Envido)]
    assert envites and all(type(e.tantos) is int for e in envites)


def test_un_bot_colgado_no_hace_perder_a_los_demas():
    hilos = threading.active_count()
    enfrentar(_fabrica(Colgado), "random", partidas=2, seed=1, vigilar=True, limite_segundos=0.2)
    # El proceso del colgado se ha matado: los que juegan después no pierden por tiempo.
    r = enfrentar("reglas", "basico", partidas=6, seed=2, vigilar=True, limite_segundos=0.5)
    assert r.faltas_a == r.faltas_b == 0
    assert threading.active_count() == hilos  # no se queda ningún hilo esperando
    cerrar_cajas()
    assert multiprocessing.active_children() == []


def test_un_archivo_que_se_cuelga_al_importarse(tmp_path):
    ruta = tmp_path / "eterno.py"
    ruta.write_text("while True:\n    pass\n", encoding="utf-8")
    inicio = time.perf_counter()
    r = enfrentar(str(ruta), "random", partidas=6, seed=1, vigilar=True, limite_segundos=0.2)
    assert r.faltas_a == 6 and r.victorias_a == 0
    assert any("no ha respondido" in m for m in r.motivos_a)
    assert time.perf_counter() - inicio < 15  # solo se espera una vez, no en cada partida


def test_lo_que_escribe_el_bot_llega_al_chat():
    caja = Caja()
    try:
        jugadores = [JugadorVigilado(caja, a, _fabrica(Hablador), a) for a in range(4)]
        match = Match(jugadores, seed=1)
        asiento = match.state.turno
        match.step()
        assert [(m.asiento, m.texto) for m in match.chat.mensajes] == [(asiento, "juego Mus")]
    finally:
        caja.cerrar()


def test_un_bot_externo_con_dataclass(tmp_path):
    ruta = tmp_path / "con_dataclass.py"
    ruta.write_text(
        "from dataclasses import dataclass\nfrom musarena.player import Bot\n\n"
        "@dataclass\nclass Opciones:\n    prudencia: float = 0.5\n\n"
        "class ConDataclass(Bot):\n"
        "    def choose_action(self, observation, legal_actions):\n"
        "        return legal_actions[0]\n", encoding="utf-8")
    r = enfrentar(str(ruta), "random", partidas=2, seed=1, vigilar=True)
    assert r.faltas_a == 0, r.motivos_a

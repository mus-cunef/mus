"""Un bot que falla, se cuelga o juega ilegal pierde la partida, pero no rompe el torneo."""

import time

import pytest

from musarena.actions import IllegalActionError, Quiero
from musarena.arena import enfrentar
from musarena.player import Bot
from musarena.torneo import jugar_torneo


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


def _fabrica(clase):
    def crear(seed):
        return clase(seed=seed)
    crear.__name__ = clase.__name__
    return crear


@pytest.mark.parametrize(("clase", "motivo"), [
    (Explota, "RuntimeError"), (Ilegal, "ilegal"), (Colgado, "no ha respondido"),
    (NoSeCrea, "al crear"),
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

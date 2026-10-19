import json

import pytest

from musarena.arena import enfrentar
from musarena.players.externos import buscar_bots, cargar_clase, es_bot_externo, nombre_externo
from musarena.torneo import ResultadoTorneo, jugar_torneo, main, participantes_por_defecto

BOT_EXTERNO = '''
from musarena.player import Bot

class SiempreLoPrimero(Bot):
    tipo = "lo_primero"

    def choose_action(self, observation, legal_actions):
        return legal_actions[0]
'''


@pytest.fixture
def carpeta_bots(tmp_path):
    carpeta = tmp_path / "bots"
    carpeta.mkdir()
    (carpeta / "lo_primero.py").write_text(BOT_EXTERNO, encoding="utf-8")
    (carpeta / "_privado.py").write_text(BOT_EXTERNO, encoding="utf-8")  # se ignora
    return carpeta


# --- Bots externos ---


def test_bots_externos(carpeta_bots):
    (ruta,) = buscar_bots(carpeta_bots)
    assert es_bot_externo(ruta) and es_bot_externo(ruta + ":SiempreLoPrimero")
    assert not es_bot_externo("reglas") and not es_bot_externo("inteligente:modelo.npz")
    assert cargar_clase(ruta).__name__ == "SiempreLoPrimero"
    assert nombre_externo(ruta) == "lo_primero"
    r = enfrentar(ruta, "random", partidas=4, seed=1)  # en la arena, por su ruta
    assert r.partidas == 4


def test_un_archivo_de_bot_que_no_vale(tmp_path):
    vacio = tmp_path / "vacio.py"
    vacio.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_clase(str(vacio))
    with pytest.raises(ValueError):
        cargar_clase(str(tmp_path / "no_existe.py"))


def test_el_bot_de_ejemplo_de_la_carpeta_bots():
    assert "bots/prudente.py" in participantes_por_defecto("bots")
    assert nombre_externo("bots/prudente.py") == "prudente"


# --- Torneo ---


def _torneo(carpeta_bots=None, procesos=1, progreso=None):
    participantes = ["random", "basico", "reglas"]
    if carpeta_bots is not None:
        participantes += buscar_bots(carpeta_bots)
    return jugar_torneo(participantes, partidas_por_cruce=6, seed=3, procesos=procesos,
                        al_progreso=progreso)


def test_torneo_todos_contra_todos(carpeta_bots):
    avisos = []
    r = _torneo(carpeta_bots, progreso=lambda hechas, total: avisos.append((hechas, total)))
    n = len(r.participantes)
    assert len(r.cruces) == n * (n - 1) // 2
    assert all(partidas == 6 for _, partidas in r.cruces.values())
    assert avisos[-1][0] == avisos[-1][1] == 6 * len(r.cruces)  # el progreso llega al 100 %
    tabla = r.tabla()
    assert [f.puesto for f in tabla] == list(range(1, n + 1))
    assert all(f.partidas == 6 * (n - 1) for f in tabla)
    assert sum(f.victorias for f in tabla) == sum(p for _, p in r.cruces.values())
    assert [f.elo for f in tabla] == sorted((f.elo for f in tabla), reverse=True)
    assert sum(f.elo for f in tabla) / n == pytest.approx(1500, abs=1e-6)  # media 1500


def test_el_elo_ordena_por_fuerza():
    """Con resultados inventados, quien más gana tiene más Elo y el cruce se respeta."""
    r = ResultadoTorneo(["a", "b", "c"], 100, 3, 0,
                        {("a", "b"): (80, 100), ("a", "c"): (90, 100), ("b", "c"): (70, 100)})
    elo = r.elo()
    assert elo["a"] > elo["b"] > elo["c"]
    assert r.victorias("b", "a") == (20, 100)
    # El Elo predice el cruce: 1 / (1 + 10^(-diferencia/400)) ≈ lo que pasó.
    prediccion = 1 / (1 + 10 ** ((elo["b"] - elo["a"]) / 400))
    assert prediccion == pytest.approx(0.8, abs=0.08)


def test_el_resultado_se_guarda_en_json_y_markdown(carpeta_bots):
    r = _torneo(carpeta_bots)
    datos = json.loads(json.dumps(r.a_dict()))
    assert [f["puesto"] for f in datos["clasificacion"]] == [1, 2, 3, 4]
    otro = ResultadoTorneo.desde_dict(datos)
    assert otro.tabla() == r.tabla()
    md = r.a_markdown()
    assert "| Puesto | Bot |" in md and "`lo_primero`" in md and "## Cruces" in md
    assert "elo" in str(r) and "1. " in str(r)


def test_el_torneo_en_paralelo_da_lo_mismo():
    assert _torneo(procesos=2).cruces == _torneo(procesos=1).cruces


def test_participantes_que_no_valen():
    with pytest.raises(ValueError):
        jugar_torneo(["random"])
    with pytest.raises(ValueError):
        jugar_torneo(["random", "random"])
    with pytest.raises(ValueError):
        jugar_torneo(["random", "humano"])


def test_mus_torneo(tmp_path, capsys):
    salida_json, salida_md = tmp_path / "c.json", tmp_path / "c.md"
    main(["--participantes", "random,basico", "-n", "4", "-p", "1",
          "--json", str(salida_json), "--markdown", str(salida_md)])
    assert "100 %" in capsys.readouterr().out
    assert json.loads(salida_json.read_text(encoding="utf-8"))["partidas_por_cruce"] == 4
    assert "Clasificación" in salida_md.read_text(encoding="utf-8")

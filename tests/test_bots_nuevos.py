"""Examen automático de cada bot de la carpeta ``bots/`` (requisito 2.2).

Se ejecuta en la CI en cada Pull Request: un bot nuevo solo se fusiona si pasa todo esto.

- Se puede cargar y define **una** clase de bot, con un ``tipo`` propio que no choca con los
  bots de la librería ni con los demás de la carpeta.
- Juega partidas completas contra ``random`` y contra ``reglas`` **sin ninguna falta**: no lanza
  errores, nunca devuelve una jugada ilegal y no tarda más de 2 segundos en ninguna jugada.
- Es reproducible: con la misma semilla juega exactamente igual.
"""

import pytest

from musarena.arena import enfrentar
from musarena.player import Player
from musarena.players import TIPOS
from musarena.players.externos import buscar_bots, cargar_clase, crear_externo

BOTS = buscar_bots("bots")


def test_hay_al_menos_un_bot_de_ejemplo():
    assert "bots/prudente.py" in BOTS


@pytest.mark.parametrize("bot", BOTS)
def test_se_carga_y_tiene_un_tipo_propio(bot):
    clase = cargar_clase(bot)
    assert issubclass(clase, Player)
    tipo = getattr(clase, "tipo", "bot")
    assert tipo != "bot", "Pon un `tipo` propio a la clase (el nombre con el que aparece)"
    assert tipo not in TIPOS, f"El tipo {tipo!r} ya existe en la librería"
    otros = [getattr(cargar_clase(b), "tipo", "bot") for b in BOTS if b != bot]
    assert tipo not in otros, f"Otro bot de bots/ ya se llama {tipo!r}"
    assert isinstance(crear_externo(bot, seed=1), Player)


@pytest.mark.parametrize("rival", ["random", "reglas"])
@pytest.mark.parametrize("bot", BOTS)
def test_juega_partidas_completas_sin_faltas(bot, rival):
    r = enfrentar(bot, rival, partidas=6, seed=11, vigilar=True, limite_segundos=2.0)
    assert r.faltas_a == 0, f"{bot} comete faltas: {'; '.join(r.motivos_a)}"
    assert r.partidas == 6


@pytest.mark.parametrize("bot", BOTS)
def test_es_reproducible_con_la_misma_semilla(bot):
    primera = enfrentar(bot, "random", partidas=2, seed=5, vigilar=True)
    segunda = enfrentar(bot, "random", partidas=2, seed=5, vigilar=True)
    assert (primera.victorias_a, primera.vacas_a, primera.vacas_b) == \
        (segunda.victorias_a, segunda.vacas_a, segunda.vacas_b), \
        "Usa self.rng (el generador del Bot) en vez de random para que se pueda repetir"

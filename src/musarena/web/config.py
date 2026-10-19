"""Opciones de la web, con valores seguros para internet.

Todo se puede cambiar con variables de entorno, sin tocar el código. ``MUS_PUBLICO=1`` activa
el **modo internet**: límites más estrictos para que un solo visitante no pueda acaparar el
servidor (pocas partidas por torneo, menos mesas abiertas).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.environ.get(nombre, defecto))
    except ValueError:
        return defecto


@dataclass(frozen=True)
class Config:
    publico: bool = False
    #: Mesas abiertas a la vez como máximo (las más antiguas sin actividad se cierran antes).
    max_mesas: int = 200
    #: Minutos sin actividad tras los que se cierra una mesa.
    minutos_inactiva: int = 120
    #: Segundos entre jugada y jugada de los bots (para que se vea lo que hacen).
    pausa_bots: float = 0.8
    #: Partidas por cruce como máximo en un torneo lanzado desde la web.
    max_partidas_torneo: int = 400
    #: Procesos para los torneos (0 = todos los núcleos).
    procesos_torneo: int = 0
    #: Longitud máxima de un mensaje del chat.
    max_chat: int = 200
    #: Dónde se graban las partidas con humanos (vacío = no se graban).
    carpeta_partidas: str = "partidas"
    #: Carpeta con bots externos que pueden participar (la del servidor, nunca la del usuario).
    carpeta_bots: str = "bots"
    #: Archivo con la última clasificación publicada.
    clasificacion: str = "docs/clasificacion.json"
    #: Archivo con las reglas.
    reglas: str = "docs/reglas.md"

    @classmethod
    def desde_entorno(cls) -> Config:
        publico = os.environ.get("MUS_PUBLICO", "0") == "1"
        return cls(
            publico=publico,
            max_mesas=_entero("MUS_MAX_MESAS", 50 if publico else 200),
            minutos_inactiva=_entero("MUS_MINUTOS_INACTIVA", 60 if publico else 120),
            max_partidas_torneo=_entero("MUS_MAX_PARTIDAS_TORNEO", 60 if publico else 400),
            procesos_torneo=_entero("MUS_PROCESOS_TORNEO", 2 if publico else 0),
            carpeta_partidas=os.environ.get("MUS_PARTIDAS", "partidas"),
            carpeta_bots=os.environ.get("MUS_BOTS", "bots"),
            clasificacion=os.environ.get("MUS_CLASIFICACION", "docs/clasificacion.json"),
            reglas=os.environ.get("MUS_REGLAS", "docs/reglas.md"),
        )

    def ruta(self, nombre: str) -> Path:
        return Path(getattr(self, nombre))

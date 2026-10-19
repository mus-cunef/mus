"""Torneos lanzados desde la web: uno a la vez, en segundo plano y con su progreso.

Usa exactamente :func:`musarena.torneo.jugar_torneo`, el mismo que ``mus-torneo`` y la GitHub
Action. Mientras se juega, el navegador pregunta por el progreso; al terminar recibe
:meth:`~musarena.torneo.ResultadoTorneo.a_dict` (clasificación y cruces).

Para que un visitante no acapare el servidor: solo puede haber **un torneo en marcha**, las
partidas por cruce tienen un máximo (``Config.max_partidas_torneo``) y solo participan bots
de la lista del servidor.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from musarena.torneo import jugar_torneo
from musarena.web.config import Config
from musarena.web.mesas import HUMANO, ErrorMesa, tipos_permitidos

#: Recibe los mismos argumentos que :func:`musarena.torneo.jugar_torneo` (para los tests).
Jugador = Callable[..., object]


@dataclass
class EstadoTorneo:
    id: str
    participantes: list[str]
    partidas_por_cruce: int
    hechas: int = 0
    total: int = 1
    estado: str = "jugando"  # "jugando", "terminado" o "error"
    resultado: dict | None = None
    error: str | None = None
    inicio: float = field(default_factory=time.time)

    def a_dict(self) -> dict:
        return {"id": self.id, "estado": self.estado, "participantes": self.participantes,
                "partidas_por_cruce": self.partidas_por_cruce, "hechas": self.hechas,
                "total": self.total, "progreso": round(self.hechas / max(1, self.total), 4),
                "resultado": self.resultado, "error": self.error}


class GestorTorneos:
    def __init__(self, config: Config, jugar: Jugador = jugar_torneo) -> None:
        self.config = config
        self._jugar = jugar
        self._torneos: dict[str, EstadoTorneo] = {}
        self._lock = threading.Lock()

    def participantes_posibles(self) -> list[str]:
        return [t for t in tipos_permitidos(self.config) if t != HUMANO]

    def en_marcha(self) -> EstadoTorneo | None:
        return next((t for t in self._torneos.values() if t.estado == "jugando"), None)

    def lanzar(self, participantes: Sequence[str], partidas_por_cruce: int,
               en_segundo_plano: bool = True) -> EstadoTorneo:
        participantes = list(dict.fromkeys(participantes))  # sin repetidos, en su orden
        posibles = set(self.participantes_posibles())
        if len(participantes) < 2:
            raise ErrorMesa("Elige al menos 2 participantes")
        for p in participantes:
            if p not in posibles:
                raise ErrorMesa(f"Participante no permitido: {p!r}")
        if not 2 <= partidas_por_cruce <= self.config.max_partidas_torneo:
            raise ErrorMesa(f"Las partidas por cruce tienen que estar entre 2 y "
                            f"{self.config.max_partidas_torneo}")
        with self._lock:
            if self.en_marcha() is not None:
                raise ErrorMesa("Ya hay un torneo en marcha; espera a que termine", 409)
            estado = EstadoTorneo(secrets.token_urlsafe(9), participantes, partidas_por_cruce)
            self._torneos = {k: v for k, v in list(self._torneos.items())[-9:]}  # los 10 últimos
            self._torneos[estado.id] = estado

        def progreso(hechas: int, total: int) -> None:
            estado.hechas, estado.total = hechas, total

        def trabajo() -> None:
            try:
                resultado = self._jugar(participantes, partidas_por_cruce,
                                        procesos=self.config.procesos_torneo,
                                        al_progreso=progreso)
                estado.resultado = resultado.a_dict()
                estado.estado = "terminado"
            except Exception as e:  # el error se enseña en la web en vez de perderse
                estado.error = str(e)
                estado.estado = "error"

        if en_segundo_plano:
            threading.Thread(target=trabajo, daemon=True).start()
        else:
            trabajo()
        return estado

    def obtener(self, torneo_id: str) -> EstadoTorneo:
        estado = self._torneos.get(torneo_id)
        if estado is None:
            raise ErrorMesa("Ese torneo no existe", 404)
        return estado

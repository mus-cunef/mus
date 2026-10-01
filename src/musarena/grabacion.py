"""Grabar y reproducir partidas (sobre todo las de humanos, para entrenar y medir).

Una partida se guarda como **la semilla del reparto y la lista de acciones** de cada asiento,
en un archivo JSON pequeño. Como el motor es determinista (el azar sale de la semilla), con eso
se reconstruye exactamente cada estado y lo que vio cada jugador en cada decisión
(:func:`reproducir`). Así los archivos no dependen de cómo codifique la red las observaciones:
siguen valiendo aunque la codificación cambie.

Uso::

    grabador = Grabador(seed=7, mejor_de=3, jugadores=["humano", "reglas", "inteligente", "reglas"])
    match = Match(mesa, seed=7, al_decidir=grabador)
    match.play()
    grabador.guardar(match)                       # partidas/2026-10-01_183012_7.json

    for partida in cargar_partidas("partidas"):
        for decision in reproducir(partida):      # Decision(asiento, observacion, legales, accion)
            ...
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from musarena import __version__
from musarena.actions import (
    Action,
    Descarte,
    Envido,
    Mus,
    NoHayMus,
    NoQuiero,
    Ordago,
    Paso,
    Quiero,
    Reenvido,
)
from musarena.cards import Carta, Palo
from musarena.engine import apply, legal_actions, nueva_partida
from musarena.match import Decision, Match
from musarena.observation import observe
from musarena.state import State

#: Versión del formato de los archivos.
FORMATO = 1

#: Carpeta donde se guardan las partidas si no se indica otra.
CARPETA_POR_DEFECTO = Path("partidas")

_SIN_DATOS = {"Mus": Mus, "NoHayMus": NoHayMus, "Paso": Paso, "Ordago": Ordago,
              "Quiero": Quiero, "NoQuiero": NoQuiero}


def accion_a_dict(accion: Action) -> dict:
    """Acción -> diccionario que se puede guardar en JSON."""
    nombre = type(accion).__name__
    if isinstance(accion, Descarte):
        cartas = sorted((c.numero, c.palo.value) for c in accion.cartas)
        return {"tipo": nombre, "cartas": [list(c) for c in cartas]}
    if isinstance(accion, (Envido, Reenvido)):
        return {"tipo": nombre, "tantos": accion.tantos}
    return {"tipo": nombre}


def accion_desde_dict(datos: dict) -> Action:
    """Diccionario guardado -> acción."""
    tipo = datos["tipo"]
    if tipo == "Descarte":
        return Descarte(frozenset(Carta(n, Palo(p)) for n, p in datos["cartas"]))
    if tipo == "Envido":
        return Envido(datos["tantos"])
    if tipo == "Reenvido":
        return Reenvido(datos["tantos"])
    if tipo in _SIN_DATOS:
        return _SIN_DATOS[tipo]()
    raise ValueError(f"Acción desconocida en la partida grabada: {tipo!r}")


@dataclass
class PartidaGrabada:
    """Todo lo necesario para repetir una partida."""

    seed: int
    mejor_de: int
    jugadores: list[str]  # tipo de cada asiento ("humano", "reglas", "inteligente"…)
    acciones: list[tuple[int, dict]] = field(default_factory=list)  # (asiento, acción)
    terminada: bool = False
    ganador: int | None = None
    fecha: str = ""
    version: str = __version__
    formato: int = FORMATO

    def guardar(self, ruta: str | Path) -> Path:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")
        return ruta

    @classmethod
    def cargar(cls, ruta: str | Path) -> PartidaGrabada:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        if datos.get("formato") != FORMATO:
            raise ValueError(f"{ruta}: formato {datos.get('formato')} no soportado")
        datos["acciones"] = [(a, accion) for a, accion in datos["acciones"]]
        return cls(**datos)


class Grabador:
    """Se pasa a :class:`~musarena.match.Match` como ``al_decidir`` y apunta cada acción."""

    def __init__(self, seed: int, mejor_de: int, jugadores: Sequence[str]) -> None:
        self.partida = PartidaGrabada(seed=seed, mejor_de=mejor_de, jugadores=list(jugadores),
                                      fecha=datetime.now().isoformat(timespec="seconds"))

    def __call__(self, decision: Decision) -> None:
        self.partida.acciones.append((decision.asiento, accion_a_dict(decision.accion)))

    def guardar(self, match: Match, carpeta: str | Path = CARPETA_POR_DEFECTO) -> Path:
        """Guarda la partida (terminada o no) y devuelve la ruta del archivo."""
        self.partida.terminada = match.terminada
        self.partida.ganador = match.ganador
        momento = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return self.partida.guardar(Path(carpeta) / f"{momento}_{self.partida.seed}.json")


def _repetir(partida: PartidaGrabada) -> Iterator[tuple[Decision, State]]:
    s = nueva_partida(mejor_de=partida.mejor_de, seed=partida.seed)
    for asiento, datos in partida.acciones:
        if s.turno != asiento:
            raise ValueError(f"La partida grabada no cuadra: le toca al asiento {s.turno}, "
                             f"no al {asiento}")
        accion = accion_desde_dict(datos)
        observacion = observe(s, asiento)
        legales = tuple(legal_actions(s))
        s = apply(s, accion)
        yield Decision(asiento, observacion, legales, accion), s


def reproducir(partida: PartidaGrabada) -> Iterator[Decision]:
    """Repite la partida y devuelve cada decisión con la observación que tenía el jugador.

    Si una acción ya no es legal (por ejemplo, porque cambiaron las reglas desde que se grabó),
    lanza :class:`~musarena.actions.IllegalActionError`.
    """
    for decision, _ in _repetir(partida):
        yield decision


def estado_final(partida: PartidaGrabada) -> State:
    """Estado al terminar la partida grabada (o donde se interrumpió)."""
    final = nueva_partida(mejor_de=partida.mejor_de, seed=partida.seed)
    for _, final in _repetir(partida):  # noqa: B007 (solo interesa el último estado)
        pass
    return final


def cargar_partidas(carpeta: str | Path = CARPETA_POR_DEFECTO) -> list[PartidaGrabada]:
    """Todas las partidas guardadas en ``carpeta`` (las más antiguas primero)."""
    return [PartidaGrabada.cargar(r) for r in sorted(Path(carpeta).glob("*.json"))]


__all__ = ["CARPETA_POR_DEFECTO", "Grabador", "PartidaGrabada", "accion_a_dict",
           "accion_desde_dict", "cargar_partidas", "estado_final", "reproducir"]

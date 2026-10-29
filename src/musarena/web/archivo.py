"""Archivo de partidas de la web, para entrenar algún día al bot con partidas humanas.

En internet el disco del servidor se borra en cada reinicio, así que las partidas con humanos
se guardan en la base de datos (la misma de las cuentas, ``MUS_BD``):

- Las **mesas normales** (humanos contra bots o entre ellos): al terminar cada mano y al
  acabar la partida, en la tabla ``partidas_web``. Si el servidor se duerme a mitad de partida,
  queda guardado hasta la última mano jugada.
- Las de los **torneos privados** ya se guardan jugada a jugada en ``partidos``.

Se guarda solo lo necesario para repetir la partida: la semilla del reparto, qué hay en cada
asiento (``"humano"``, ``"inteligente"``…) y las jugadas. **Ni nombres ni cuentas**.

Para entrenar se exportan a archivos como los de ``mus-play`` (:mod:`musarena.grabacion`)::

    $env:MUS_BD = "postgresql://..."            # la cadena de Neon (PowerShell)
    python -m musarena.web.archivo partidas/web

y se usan con :func:`musarena.ia.entrenamiento.datos.de_partidas`.
"""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, insert, select, update

from musarena import __version__
from musarena.grabacion import PartidaGrabada
from musarena.web.bd import conectar, partidas_web, partidos
from musarena.web.mesas import HUMANO, Mesa


class ArchivoPartidas:
    """Guarda las partidas de las mesas normales en la base de datos."""

    def __init__(self, motor: Engine, reloj: Callable[[], float] = time.time) -> None:
        self.motor = motor
        self.reloj = reloj

    def guardar(self, mesa: Mesa) -> None:
        """Guarda (o actualiza) la partida de una mesa."""
        if not mesa.acciones:
            return
        valores = {"seed": mesa.seed, "mejor_de": mesa.mejor_de, "jugadores": list(mesa.tipos),
                   "acciones": list(mesa.acciones), "terminada": mesa.match.terminada,
                   "ganador": mesa.match.ganador, "actualizado": self.reloj()}
        with self.motor.begin() as c:
            hecho = c.execute(update(partidas_web).where(partidas_web.c.mesa == mesa.id)
                              .values(**valores))
            if hecho.rowcount == 0:
                c.execute(insert(partidas_web).values(mesa=mesa.id, creada=self.reloj(),
                                                      version=__version__, **valores))


def _fecha(segundos: float | None) -> str:
    return datetime.fromtimestamp(segundos or 0).isoformat(timespec="seconds")


def partidas_guardadas(motor: Engine) -> list[tuple[str, PartidaGrabada]]:
    """Todas las partidas guardadas (mesas normales y torneos), con un nombre para cada una."""
    salida = []
    with motor.connect() as c:
        for f in c.execute(select(partidas_web).order_by(partidas_web.c.id)):
            salida.append((f"web_{f.id}", PartidaGrabada(
                seed=f.seed, mejor_de=f.mejor_de, jugadores=list(f.jugadores),
                acciones=[(a, d) for a, d in f.acciones], terminada=f.terminada,
                ganador=f.ganador, fecha=_fecha(f.creada), version=f.version or "")))
        for f in c.execute(select(partidos).where(partidos.c.acciones.is_not(None))
                           .order_by(partidos.c.id)):
            if not f.acciones or f.semilla is None:
                continue
            terminada = f.estado == "terminado" and not f.pase
            ganador = None
            if terminada:
                ganador = 0 if f.ganador == f.pareja_a else 1
            salida.append((f"torneo_{f.id}", PartidaGrabada(
                seed=f.semilla, mejor_de=f.mejor_de, jugadores=[HUMANO] * 4,
                acciones=[(a, d) for a, d in f.acciones], terminada=terminada,
                ganador=ganador, fecha=_fecha(f.actualizado))))
    return salida


def exportar(motor: Engine, carpeta: str | Path) -> int:
    """Escribe cada partida guardada como un archivo JSON en ``carpeta`` (las que ya están se
    sobrescriben, por si han avanzado). Devuelve cuántas se han escrito."""
    carpeta = Path(carpeta)
    partidas = partidas_guardadas(motor)
    for nombre, partida in partidas:
        partida.guardar(carpeta / f"{nombre}.json")
    return len(partidas)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m musarena.web.archivo",
        description="Exporta las partidas guardadas por la web a archivos JSON para entrenar.")
    parser.add_argument("carpeta", nargs="?", default="partidas/web")
    parser.add_argument("--bd", default=os.environ.get("MUS_BD", ""),
                        help="URL de la base de datos (por defecto, la variable MUS_BD)")
    args = parser.parse_args(argv)
    if not args.bd:
        parser.error("Falta la base de datos: pon la variable MUS_BD o usa --bd")
    from musarena.web.config import _url_bd

    n = exportar(conectar(_url_bd(args.bd)), args.carpeta)
    print(f"{n} partidas exportadas a {args.carpeta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

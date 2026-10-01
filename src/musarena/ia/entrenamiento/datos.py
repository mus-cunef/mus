"""Generación de datos: juega partidas y guarda cada decisión como un ejemplo de entrenamiento.

Cada ejemplo tiene:

- ``x``: la observación codificada (:func:`~musarena.ia.codificacion.codificar`);
- ``mascara``: qué acciones del catálogo eran legales;
- ``y``: qué acción eligió el jugador (posición del catálogo);
- ``valor``: +1 si la pareja del jugador acabó ganando la vaca en la que tomó la decisión y -1
  si la perdió (para enseñar a la red a estimar cómo va la partida).

Los datos no usan información oculta: ``x`` sale solo de la observación del jugador.

Uso desde la terminal::

    python -m musarena.ia.entrenamiento.datos --partidas 5000 --salida datos/reglas.npz

Con :func:`de_partidas` se sacan los mismos ejemplos de partidas humanas grabadas.
"""

from __future__ import annotations

import argparse
import os
import random
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from musarena.grabacion import PartidaGrabada, estado_final, reproducir
from musarena.ia import acciones
from musarena.ia.codificacion import N_ENTRADAS, codificar
from musarena.match import Decision, Match
from musarena.players import crear_jugador
from musarena.state import pareja

#: Maestros por defecto: el bot de reglas con sus tres estilos, mezclados en cada mesa.
MAESTROS: tuple[str, ...] = ("reglas", "reglas:agresivo", "reglas:conservador")


def _jugar_trozo(args: tuple[int, int, tuple[str, ...], int]) -> dict[str, np.ndarray]:
    partidas, seed, tipos, mejor_de = args
    rng = random.Random(seed)
    xs, mascaras, ys, valores = [], [], [], []
    for _ in range(partidas):
        mesa = [crear_jugador(rng.choice(tipos), seed=rng.randrange(2**32)) for _ in range(4)]
        pendientes: list[tuple[int, int]] = []  # (asiento, número de vaca) de cada ejemplo

        def al_decidir(d: Decision, pendientes: list = pendientes) -> None:
            obs = d.observacion
            xs.append(codificar(obs))
            mascaras.append(acciones.mascara(d.legales, obs.cartas))
            ys.append(acciones.indice(d.accion, obs.cartas))
            pendientes.append((d.asiento, sum(obs.vacas)))

        match = Match(mesa, mejor_de=mejor_de, seed=rng.randrange(2**32), al_decidir=al_decidir)
        match.play()
        ganadoras = [m.ganador_vaca for m in match.state.manos_jugadas
                     if m.ganador_vaca is not None]
        valores.extend(1.0 if pareja(a) == ganadoras[v] else -1.0 for a, v in pendientes)
    return {
        "x": np.asarray(xs, dtype=np.float32),
        "mascara": np.asarray(mascaras, dtype=bool),
        "y": np.asarray(ys, dtype=np.int16),
        "valor": np.asarray(valores, dtype=np.float32),
    }


def generar(
    partidas: int,
    tipos: Sequence[str] = MAESTROS,
    seed: int = 0,
    mejor_de: int = 3,
    procesos: int | None = None,
) -> dict[str, np.ndarray]:
    """Juega ``partidas`` partidas entre bots de ``tipos`` (repartidos entre procesos)."""
    procesos = procesos or os.cpu_count() or 1
    trozos = min(partidas, procesos * 4)
    por_trozo = [partidas // trozos + (i < partidas % trozos) for i in range(trozos)]
    tareas = [(n, seed * 1_000_003 + i, tuple(tipos), mejor_de) for i, n in enumerate(por_trozo)]
    if procesos == 1:
        resultados = [_jugar_trozo(t) for t in tareas]
    else:
        with ProcessPoolExecutor(procesos) as ex:
            resultados = list(ex.map(_jugar_trozo, tareas))
    return {k: np.concatenate([r[k] for r in resultados]) for k in resultados[0]}


def de_partidas(partidas: Sequence[PartidaGrabada], tipos: Sequence[str] = ("humano",)
                ) -> dict[str, np.ndarray]:
    """Ejemplos de entrenamiento con las decisiones de los asientos de ``tipos`` (por defecto,
    las de los humanos) en partidas grabadas con :mod:`musarena.grabacion`.

    El valor de cada decisión es +1 o -1 según quién ganó esa vaca; las decisiones de una vaca
    que se quedó a medias (partida interrumpida) no se usan.
    """
    xs, mascaras, ys, valores = [], [], [], []
    for partida in partidas:
        elegidos = {a for a, t in enumerate(partida.jugadores) if t in tipos}
        if not elegidos:
            continue
        ganadoras = [m.ganador_vaca for m in estado_final(partida).manos_jugadas
                     if m.ganador_vaca is not None]
        for d in reproducir(partida):
            vaca = sum(d.observacion.vacas)
            if d.asiento not in elegidos or vaca >= len(ganadoras):
                continue
            obs = d.observacion
            xs.append(codificar(obs))
            mascaras.append(acciones.mascara(d.legales, obs.cartas))
            ys.append(acciones.indice(d.accion, obs.cartas))
            valores.append(1.0 if pareja(d.asiento) == ganadoras[vaca] else -1.0)
    return {
        "x": np.asarray(xs, dtype=np.float32).reshape(-1, N_ENTRADAS),
        "mascara": np.asarray(mascaras, dtype=bool).reshape(-1, acciones.N_ACCIONES),
        "y": np.asarray(ys, dtype=np.int16),
        "valor": np.asarray(valores, dtype=np.float32),
    }


def guardar(datos: dict[str, np.ndarray], ruta: str | Path) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(ruta, **{**datos, "x": datos["x"].astype(np.float16)})


def cargar(ruta: str | Path) -> dict[str, np.ndarray]:
    with np.load(ruta) as d:
        datos = {k: d[k] for k in d.files}
    datos["x"] = datos["x"].astype(np.float32)
    return datos


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera datos de entrenamiento jugando.")
    parser.add_argument("--partidas", type=int, default=2000)
    parser.add_argument("--tipos", default=",".join(MAESTROS))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--salida", default="datos/reglas.npz")
    args = parser.parse_args(argv)
    datos = generar(args.partidas, args.tipos.split(","), args.seed)
    guardar(datos, args.salida)
    print(f"{len(datos['y'])} decisiones de {args.partidas} partidas en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

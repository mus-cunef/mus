"""Arena: enfrenta dos tipos de bot en muchas partidas y mide quién gana.

Sirve para comprobar que un bot es mejor que otro (por ejemplo, el heurístico frente al
aleatorio) y, más adelante, para medir el progreso del bot entrenado y montar torneos.

Para que la comparación sea justa:

- Las partidas se juegan **por parejas de repartos**: cada semilla de reparto se juega dos veces
  intercambiando los asientos, así los dos bots reciben las mismas cartas y la misma ventaja de
  ser mano. Esto reduce mucho la suerte en el resultado.
- Todo sale de una semilla, así que un enfrentamiento se puede repetir exactamente.

Uso desde la terminal::

    mus-arena reglas random --partidas 200
    mus-arena inteligente:checkpoints/mejor.npz reglas -n 2000 --procesos 0
"""

from __future__ import annotations

import argparse
import math
import os
import random
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from musarena.match import Match
from musarena.player import Player
from musarena.players import BOTS, crear_jugador, es_tipo_valido
from musarena.state import pareja


@dataclass(frozen=True)
class ResultadoArena:
    tipo_a: str
    tipo_b: str
    partidas: int
    victorias_a: int
    vacas_a: int
    vacas_b: int

    @property
    def victorias_b(self) -> int:
        return self.partidas - self.victorias_a

    @property
    def porcentaje_a(self) -> float:
        return self.victorias_a / self.partidas

    @property
    def margen_95(self) -> float:
        """Margen de error aproximado (95 %) del porcentaje de victorias."""
        p = self.porcentaje_a
        return 1.96 * math.sqrt(p * (1 - p) / self.partidas)

    def __str__(self) -> str:
        return (
            f"{self.tipo_a} contra {self.tipo_b}: {self.victorias_a}-{self.victorias_b} "
            f"en {self.partidas} partidas ({self.porcentaje_a:.1%} ± {self.margen_95:.1%}); "
            f"vacas {self.vacas_a}-{self.vacas_b}"
        )


#: Crea un jugador a partir de una semilla (para enfrentar bots con parámetros a medida).
Fabrica = Callable[[int], Player]


def fabrica(tipo: str | Fabrica) -> Fabrica:
    """Convierte ``"reglas"``, ``"reglas:agresivo"`` (tipo y estilo) o una función en fábrica."""
    if callable(tipo):
        return tipo
    if tipo.partition(":")[0] not in BOTS or not es_tipo_valido(tipo):
        raise ValueError(f"En la arena solo juegan bots: {', '.join(BOTS)} (y estilos de reglas)")
    return lambda seed: crear_jugador(tipo, seed=seed)


def _trozo(args: tuple[str | Fabrica, str | Fabrica, int, int, int]) -> ResultadoArena:
    tipo_a, tipo_b, partidas, mejor_de, seed = args
    return enfrentar(tipo_a, tipo_b, partidas, mejor_de, seed)


def enfrentar(
    tipo_a: str | Fabrica,
    tipo_b: str | Fabrica,
    partidas: int = 100,
    mejor_de: int = 3,
    seed: int = 0,
    procesos: int = 1,
) -> ResultadoArena:
    """Juega ``partidas`` partidas entre una pareja de ``tipo_a`` y otra de ``tipo_b``.

    Cada tipo puede ser un nombre del registro (``"reglas"``), un nombre con estilo
    (``"reglas:agresivo"``), un modelo (``"inteligente:ruta.npz"``) o una función
    ``seed -> Player``. Con ``procesos`` > 1 las partidas se reparten entre varios procesos
    (cada trozo con su propia semilla, así que el resultado es otro, igual de reproducible);
    en ese caso las funciones tienen que poder enviarse a otro proceso (no valen lambdas).
    """
    crear = {"a": fabrica(tipo_a), "b": fabrica(tipo_b)}
    nombres = [t if isinstance(t, str) else getattr(t, "__name__", "bot") for t in (tipo_a, tipo_b)]
    if procesos > 1 and partidas >= 4:
        trozos = min(procesos * 4, partidas // 2)
        pares = partidas // 2  # cada reparto se juega dos veces
        por_trozo = [2 * (pares // trozos + (i < pares % trozos)) for i in range(trozos)]
        por_trozo[-1] += partidas % 2
        tareas = [(tipo_a, tipo_b, n, mejor_de, seed * 1_000_003 + i)
                  for i, n in enumerate(por_trozo)]
        with ProcessPoolExecutor(procesos) as ex:
            res = list(ex.map(_trozo, tareas))
        return ResultadoArena(nombres[0], nombres[1], partidas,
                              sum(r.victorias_a for r in res), sum(r.vacas_a for r in res),
                              sum(r.vacas_b for r in res))
    semillas = random.Random(seed)
    victorias_a = vacas_a = vacas_b = 0
    semilla_reparto = 0
    for i in range(partidas):
        a_en_pareja_0 = i % 2 == 0
        if a_en_pareja_0:
            semilla_reparto = semillas.randrange(2**32)  # la partida siguiente repite reparto
        jugadores = []
        for asiento in range(4):
            es_a = (pareja(asiento) == 0) == a_en_pareja_0
            jugadores.append(crear["a" if es_a else "b"](semillas.randrange(2**32)))
        match = Match(jugadores, mejor_de=mejor_de, seed=semilla_reparto)
        ganadora = match.play()
        pareja_a = 0 if a_en_pareja_0 else 1
        victorias_a += ganadora == pareja_a
        vacas_a += match.state.vacas[pareja_a]
        vacas_b += match.state.vacas[1 - pareja_a]
    return ResultadoArena(nombres[0], nombres[1], partidas, victorias_a, vacas_a, vacas_b)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mus-arena", description="Enfrenta dos tipos de bot.")
    ayuda = (f"bot: {', '.join(BOTS)} (con estilo: reglas:agresivo; con modelo: "
             f"inteligente:ruta.npz)")
    parser.add_argument("tipo_a", help=ayuda)
    parser.add_argument("tipo_b", help=ayuda)
    parser.add_argument("-n", "--partidas", type=int, default=100)
    parser.add_argument("--mejor-de", type=int, choices=(3, 5), default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-p", "--procesos", type=int, default=1,
                        help="procesos en paralelo (0 = todos los núcleos)")
    args = parser.parse_args(argv)
    procesos = args.procesos or os.cpu_count() or 1
    print(enfrentar(args.tipo_a, args.tipo_b, args.partidas, args.mejor_de, args.seed, procesos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

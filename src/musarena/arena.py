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
"""

from __future__ import annotations

import argparse
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from musarena.match import Match
from musarena.players import BOTS, crear_jugador
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


def enfrentar(
    tipo_a: str,
    tipo_b: str,
    partidas: int = 100,
    mejor_de: int = 3,
    seed: int = 0,
) -> ResultadoArena:
    """Juega ``partidas`` partidas entre una pareja de ``tipo_a`` y otra de ``tipo_b``."""
    for tipo in (tipo_a, tipo_b):
        if tipo not in BOTS:
            raise ValueError(f"En la arena solo juegan bots: {list(BOTS)}")
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
            jugadores.append(
                crear_jugador(tipo_a if es_a else tipo_b, seed=semillas.randrange(2**32))
            )
        match = Match(jugadores, mejor_de=mejor_de, seed=semilla_reparto)
        ganadora = match.play()
        pareja_a = 0 if a_en_pareja_0 else 1
        victorias_a += ganadora == pareja_a
        vacas_a += match.state.vacas[pareja_a]
        vacas_b += match.state.vacas[1 - pareja_a]
    return ResultadoArena(tipo_a, tipo_b, partidas, victorias_a, vacas_a, vacas_b)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mus-arena", description="Enfrenta dos tipos de bot.")
    parser.add_argument("tipo_a", choices=BOTS)
    parser.add_argument("tipo_b", choices=BOTS)
    parser.add_argument("-n", "--partidas", type=int, default=100)
    parser.add_argument("--mejor-de", type=int, choices=(3, 5), default=3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    print(enfrentar(args.tipo_a, args.tipo_b, args.partidas, args.mejor_de, args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

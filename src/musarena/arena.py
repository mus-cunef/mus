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
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from musarena.match import Match
from musarena.player import Player
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


#: Crea un jugador a partir de una semilla (para enfrentar bots con parámetros a medida).
Fabrica = Callable[[int], Player]


def fabrica(tipo: str | Fabrica) -> Fabrica:
    """Convierte ``"reglas"``, ``"reglas:agresivo"`` (tipo y estilo) o una función en fábrica."""
    if callable(tipo):
        return tipo
    base, _, estilo = tipo.partition(":")
    if base not in BOTS:
        raise ValueError(f"En la arena solo juegan bots: {', '.join(BOTS)}")
    extra = {"estilo": estilo} if estilo else {}
    return lambda seed: crear_jugador(base, seed=seed, **extra)


def enfrentar(
    tipo_a: str | Fabrica,
    tipo_b: str | Fabrica,
    partidas: int = 100,
    mejor_de: int = 3,
    seed: int = 0,
) -> ResultadoArena:
    """Juega ``partidas`` partidas entre una pareja de ``tipo_a`` y otra de ``tipo_b``.

    Cada tipo puede ser un nombre del registro (``"reglas"``), un nombre con estilo
    (``"reglas:agresivo"``) o una función ``seed -> Player``.
    """
    crear = {"a": fabrica(tipo_a), "b": fabrica(tipo_b)}
    nombres = [t if isinstance(t, str) else getattr(t, "__name__", "bot") for t in (tipo_a, tipo_b)]
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
    ayuda = f"bot: {', '.join(BOTS)} (con estilo: reglas:agresivo)"
    parser.add_argument("tipo_a", help=ayuda)
    parser.add_argument("tipo_b", help=ayuda)
    parser.add_argument("-n", "--partidas", type=int, default=100)
    parser.add_argument("--mejor-de", type=int, choices=(3, 5), default=3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    print(enfrentar(args.tipo_a, args.tipo_b, args.partidas, args.mejor_de, args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

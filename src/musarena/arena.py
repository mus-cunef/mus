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
from functools import partial

from musarena.match import Match
from musarena.player import Player
from musarena.players import BOTS, crear_jugador, es_tipo_valido
from musarena.players.externos import cargar_clase, crear_externo, es_bot_externo
from musarena.state import pareja
from musarena.vigilancia import FaltaDeBot
from musarena.vigilancia import vigilar as _vigilar


@dataclass(frozen=True)
class ResultadoArena:
    tipo_a: str
    tipo_b: str
    partidas: int
    victorias_a: int
    vacas_a: int
    vacas_b: int
    #: Partidas perdidas por faltas (el bot falló, se colgó o jugó ilegal) y algunos motivos.
    faltas_a: int = 0
    faltas_b: int = 0
    motivos_a: tuple[str, ...] = ()
    motivos_b: tuple[str, ...] = ()

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
        texto = (
            f"{self.tipo_a} contra {self.tipo_b}: {self.victorias_a}-{self.victorias_b} "
            f"en {self.partidas} partidas ({self.porcentaje_a:.1%} ± {self.margen_95:.1%}); "
            f"vacas {self.vacas_a}-{self.vacas_b}"
        )
        for nombre, faltas, motivos in ((self.tipo_a, self.faltas_a, self.motivos_a),
                                        (self.tipo_b, self.faltas_b, self.motivos_b)):
            if faltas:
                texto += (f"\n  {nombre}: {faltas} partidas perdidas por faltas "
                          f"({'; '.join(motivos)})")
        return texto


#: Crea un jugador a partir de una semilla (para enfrentar bots con parámetros a medida).
Fabrica = Callable[[int], Player]


def fabrica(tipo: str | Fabrica) -> Fabrica:
    """Convierte ``"reglas"``, ``"reglas:agresivo"`` (tipo y estilo), un archivo de bot
    (``"bots/mi_bot.py"``) o una función en fábrica."""
    if callable(tipo):
        return tipo
    if es_bot_externo(tipo):
        cargar_clase(tipo)  # falla ya si el archivo no vale, no a mitad de las partidas
        return partial(crear_externo, tipo)
    if tipo.partition(":")[0] not in BOTS or not es_tipo_valido(tipo):
        raise ValueError(f"En la arena solo juegan bots: {', '.join(BOTS)} (y estilos de reglas)")
    return lambda seed: crear_jugador(tipo, seed=seed)


def _crear_de(tipo: str, seed: int) -> Player:
    return fabrica(tipo)(seed)


def _trozo(args: tuple) -> ResultadoArena:
    tipo_a, tipo_b, partidas, mejor_de, seed, vigilar, limite = args
    return enfrentar(tipo_a, tipo_b, partidas, mejor_de, seed, vigilar=vigilar,
                     limite_segundos=limite)


def _juntar(motivos: list[str], nuevos: Sequence[str], maximo: int = 3) -> None:
    for m in nuevos:
        if m not in motivos and len(motivos) < maximo:
            motivos.append(m)


def enfrentar(
    tipo_a: str | Fabrica,
    tipo_b: str | Fabrica,
    partidas: int = 100,
    mejor_de: int = 3,
    seed: int = 0,
    procesos: int = 1,
    vigilar: bool = False,
    limite_segundos: float | None = 5.0,
) -> ResultadoArena:
    """Juega ``partidas`` partidas entre una pareja de ``tipo_a`` y otra de ``tipo_b``.

    Cada tipo puede ser un nombre del registro (``"reglas"``), un nombre con estilo
    (``"reglas:agresivo"``), un modelo (``"inteligente:ruta.npz"``) o una función
    ``seed -> Player``. Con ``procesos`` > 1 las partidas se reparten entre varios procesos
    (cada trozo con su propia semilla, así que el resultado es otro, igual de reproducible);
    en ese caso las funciones tienen que poder enviarse a otro proceso (no valen lambdas).

    Con ``vigilar=True`` (lo usa el torneo), un bot que falla, tarda más de ``limite_segundos``
    en decidir o juega ilegal **pierde esa partida** y se sigue con la siguiente (ver
    :mod:`musarena.vigilancia`); las faltas se cuentan en el resultado.
    """
    if vigilar:  # hasta cargar el bot se vigila: un archivo roto también es una falta
        crear = {k: _vigilar(partial(_crear_de, tipo) if isinstance(tipo, str) else fabrica(tipo),
                             limite_segundos) for k, tipo in (("a", tipo_a), ("b", tipo_b))}
    else:
        crear = {"a": fabrica(tipo_a), "b": fabrica(tipo_b)}
    nombres = [t if isinstance(t, str) else getattr(t, "__name__", "bot") for t in (tipo_a, tipo_b)]
    if procesos > 1 and partidas >= 4:
        trozos = min(procesos * 4, partidas // 2)
        pares = partidas // 2  # cada reparto se juega dos veces
        por_trozo = [2 * (pares // trozos + (i < pares % trozos)) for i in range(trozos)]
        por_trozo[-1] += partidas % 2
        tareas = [(tipo_a, tipo_b, n, mejor_de, seed * 1_000_003 + i, vigilar, limite_segundos)
                  for i, n in enumerate(por_trozo)]
        with ProcessPoolExecutor(procesos) as ex:
            res = list(ex.map(_trozo, tareas))
        motivos_a: list[str] = []
        motivos_b: list[str] = []
        for r in res:
            _juntar(motivos_a, r.motivos_a)
            _juntar(motivos_b, r.motivos_b)
        return ResultadoArena(nombres[0], nombres[1], partidas,
                              sum(r.victorias_a for r in res), sum(r.vacas_a for r in res),
                              sum(r.vacas_b for r in res), sum(r.faltas_a for r in res),
                              sum(r.faltas_b for r in res), tuple(motivos_a), tuple(motivos_b))
    semillas = random.Random(seed)
    victorias_a = vacas_a = vacas_b = 0
    faltas = {"a": 0, "b": 0}
    motivos: dict[str, list[str]] = {"a": [], "b": []}
    semilla_reparto = 0
    for i in range(partidas):
        a_en_pareja_0 = i % 2 == 0
        if a_en_pareja_0:
            semilla_reparto = semillas.randrange(2**32)  # la partida siguiente repite reparto
        pareja_a = 0 if a_en_pareja_0 else 1
        lado = {pareja_a: "a", 1 - pareja_a: "b"}
        jugadores = []
        culpable = None  # pareja del bot que comete una falta
        for asiento in range(4):
            es_a = (pareja(asiento) == 0) == a_en_pareja_0
            try:
                jugadores.append(crear["a" if es_a else "b"](semillas.randrange(2**32)))
            except FaltaDeBot as falta:  # solo con vigilar: el bot ni siquiera se crea
                culpable = culpable if culpable is not None else pareja(asiento)
                _juntar(motivos[lado[pareja(asiento)]], [falta.motivo])
        match = None
        if culpable is None:
            match = Match(jugadores, mejor_de=mejor_de, seed=semilla_reparto)
            try:
                ganadora = match.play()
            except FaltaDeBot as falta:
                culpable = pareja(falta.asiento)
                _juntar(motivos[lado[culpable]], [falta.motivo])
        if culpable is not None:  # pierde la pareja del bot que cometió la falta
            ganadora = 1 - culpable
            faltas[lado[culpable]] += 1
        victorias_a += ganadora == pareja_a
        if match is not None:
            vacas_a += match.state.vacas[pareja_a]
            vacas_b += match.state.vacas[1 - pareja_a]
    return ResultadoArena(nombres[0], nombres[1], partidas, victorias_a, vacas_a, vacas_b,
                          faltas["a"], faltas["b"], tuple(motivos["a"]), tuple(motivos["b"]))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mus-arena", description="Enfrenta dos tipos de bot.")
    ayuda = (f"bot: {', '.join(BOTS)} (con estilo: reglas:agresivo; con modelo: "
             f"inteligente:ruta.npz; o un archivo de bot: bots/mi_bot.py)")
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

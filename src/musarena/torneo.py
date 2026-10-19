"""Torneo: todos los bots contra todos y una clasificación.

Cada par de participantes juega ``partidas_por_cruce`` partidas con **repartos duplicados**
(como en la arena: cada reparto se juega dos veces cambiando a los bots de pareja), así que la
suerte se compensa. Con todos los resultados se calcula la clasificación:

- **% de victorias** sobre todas sus partidas, con su margen de error al 95 %;
- **puntuación Elo**: se ajusta un modelo de Bradley-Terry, en el que cada participante tiene
  una fuerza y la probabilidad de que A gane a B es ``fA / (fA + fB)``, con todos los
  enfrentamientos a la vez. Se expresa en la escala de Elo (media 1500; 200 puntos de diferencia
  ≈ 76 % de victorias). A diferencia del porcentaje, tiene en cuenta contra quién se ganó.

La misma función sirve para la terminal (``mus-torneo``), para GitHub Actions y para la web:
:func:`jugar_torneo` acepta ``al_progreso`` (para una barra de progreso) y el resultado se
convierte en un diccionario listo para JSON (:meth:`ResultadoTorneo.a_dict`) o en Markdown
(:meth:`ResultadoTorneo.a_markdown`).

Uso::

    mus-torneo                                   # todos los bots, 200 partidas por cruce
    mus-torneo -n 400 -p 0 --markdown clasificacion.md --json clasificacion.json
    mus-torneo --participantes reglas,inteligente,bots/mi_bot.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from musarena.arena import ResultadoArena, enfrentar, fabrica
from musarena.players import BOTS, OPCIONES
from musarena.players.externos import buscar_bots, es_bot_externo, nombre_externo

#: Recibe (partidas jugadas, partidas totales) cada vez que termina un trozo del torneo.
Progreso = Callable[[int, int], None]

#: Partidas de cada trozo de trabajo (par, para que cada reparto se juegue dos veces).
_TROZO = 20


def participantes_por_defecto(carpeta_bots: str | Path = "bots") -> list[str]:
    """Todos los bots del registro (con los estilos de ``reglas``) y los de ``carpeta_bots``."""
    propios = [o for o in OPCIONES if o.partition(":")[0] in BOTS]
    return propios + buscar_bots(carpeta_bots)


def nombre(participante: str) -> str:
    """Nombre corto para la clasificación."""
    if es_bot_externo(participante):
        return nombre_externo(participante)
    if participante.startswith("inteligente:"):
        return "inteligente:" + Path(participante.partition(":")[2]).stem
    return participante


@dataclass(frozen=True)
class Fila:
    """Una línea de la clasificación."""

    puesto: int
    participante: str
    nombre: str
    partidas: int
    victorias: int
    porcentaje: float
    margen_95: float
    elo: float


@dataclass
class ResultadoTorneo:
    participantes: list[str]
    partidas_por_cruce: int
    mejor_de: int
    seed: int
    #: (a, b) -> (victorias de a, partidas), con a antes que b en ``participantes``.
    cruces: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict)
    fecha: str = ""
    segundos: float = 0.0

    def victorias(self, a: str, b: str) -> tuple[int, int]:
        """(victorias de a contra b, partidas entre los dos)."""
        if (a, b) in self.cruces:
            return self.cruces[(a, b)]
        v, n = self.cruces[(b, a)]
        return n - v, n

    def elo(self, iteraciones: int = 500) -> dict[str, float]:
        """Puntuación de cada participante con el modelo de Bradley-Terry, en escala Elo.

        Se ajusta con el algoritmo MM de Hunter. A cada cruce se le suma media victoria a cada
        lado, para que un participante que no gane nunca no tenga fuerza cero (−∞ en Elo).
        """
        ps = self.participantes
        fuerza = dict.fromkeys(ps, 1.0)
        for _ in range(iteraciones):
            nueva = {}
            for i in ps:
                ganadas = denominador = 0.0
                for j in ps:
                    if i == j:
                        continue
                    v, n = self.victorias(i, j)
                    ganadas += v + 0.5
                    denominador += (n + 1) / (fuerza[i] + fuerza[j])
                nueva[i] = ganadas / denominador
            media = math.exp(sum(math.log(f) for f in nueva.values()) / len(nueva))
            fuerza = {k: f / media for k, f in nueva.items()}
        return {k: 1500 + 400 * math.log10(f) for k, f in fuerza.items()}

    def tabla(self) -> list[Fila]:
        """Clasificación ordenada de mejor a peor (por Elo)."""
        elo = self.elo()
        filas = []
        for p in self.participantes:
            v = n = 0
            for q in self.participantes:
                if q != p:
                    vq, nq = self.victorias(p, q)
                    v, n = v + vq, n + nq
            pct = v / n if n else 0.0
            margen = 1.96 * math.sqrt(pct * (1 - pct) / n) if n else 0.0
            filas.append((elo[p], p, n, v, pct, margen))
        filas.sort(key=lambda f: -f[0])
        return [Fila(i + 1, p, nombre(p), n, v, pct, margen, e)
                for i, (e, p, n, v, pct, margen) in enumerate(filas)]

    def a_dict(self) -> dict:
        """Todo el resultado como diccionario (para guardarlo en JSON o enseñarlo en la web)."""
        return {
            "fecha": self.fecha,
            "segundos": round(self.segundos, 1),
            "partidas_por_cruce": self.partidas_por_cruce,
            "mejor_de": self.mejor_de,
            "seed": self.seed,
            "participantes": self.participantes,
            "clasificacion": [
                {"puesto": f.puesto, "participante": f.participante, "nombre": f.nombre,
                 "partidas": f.partidas, "victorias": f.victorias,
                 "porcentaje": round(f.porcentaje, 4), "margen_95": round(f.margen_95, 4),
                 "elo": round(f.elo, 1)}
                for f in self.tabla()
            ],
            "cruces": [{"a": a, "b": b, "victorias_a": v, "partidas": n}
                       for (a, b), (v, n) in self.cruces.items()],
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> ResultadoTorneo:
        cruces = {(c["a"], c["b"]): (c["victorias_a"], c["partidas"]) for c in datos["cruces"]}
        return cls(datos["participantes"], datos["partidas_por_cruce"], datos["mejor_de"],
                   datos["seed"], cruces, datos.get("fecha", ""), datos.get("segundos", 0.0))

    def a_markdown(self) -> str:
        """Clasificación y tabla de cruces en Markdown (para GitHub)."""
        filas = self.tabla()
        lineas = [
            "# Clasificación del torneo de Mus Arena",
            "",
            f"{self.fecha} · {self.partidas_por_cruce} partidas por cruce, al mejor de "
            f"{self.mejor_de} vacas, con repartos duplicados · semilla {self.seed}",
            "",
            "| Puesto | Bot | Elo | Victorias | Partidas | % (± 95 %) |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for f in filas:
            lineas.append(f"| {f.puesto} | `{f.nombre}` | {f.elo:.0f} | {f.victorias} | "
                          f"{f.partidas} | {f.porcentaje:.1%} ± {f.margen_95:.1%} |")
        orden = [f.participante for f in filas]
        lineas += ["", "## Cruces", "",
                   "% de victorias del bot de la fila contra el de la columna.", "",
                   "| | " + " | ".join(f"`{nombre(p)}`" for p in orden) + " |",
                   "| --- |" + " --- |" * len(orden)]
        for a in orden:
            celdas = []
            for b in orden:
                if a == b:
                    celdas.append("—")
                else:
                    v, n = self.victorias(a, b)
                    celdas.append(f"{v / n:.0%}")
            lineas.append(f"| `{nombre(a)}` | " + " | ".join(celdas) + " |")
        return "\n".join(lineas) + "\n"

    def __str__(self) -> str:
        filas = self.tabla()
        ancho = max(len(f.nombre) for f in filas)
        lineas = [f"{'':>3}  {'bot':<{ancho}}  {'elo':>6}  {'victorias':>14}  %"]
        for f in filas:
            lineas.append(f"{f.puesto:>3}. {f.nombre:<{ancho}}  {f.elo:6.0f}  "
                          f"{f.victorias:>6}/{f.partidas:<7}  {f.porcentaje:5.1%} ± "
                          f"{f.margen_95:.1%}")
        return "\n".join(lineas)


def _trozo(args: tuple[str, str, int, int, int]) -> tuple[str, str, ResultadoArena]:
    a, b, partidas, mejor_de, seed = args
    return a, b, enfrentar(a, b, partidas=partidas, mejor_de=mejor_de, seed=seed)


def jugar_torneo(
    participantes: Sequence[str] | None = None,
    partidas_por_cruce: int = 200,
    mejor_de: int = 3,
    seed: int = 0,
    procesos: int = 1,
    al_progreso: Progreso | None = None,
) -> ResultadoTorneo:
    """Juega el torneo todos contra todos y devuelve el resultado.

    ``participantes`` son tipos de bot del registro (``"reglas:agresivo"``, ``"inteligente"``,
    ``"inteligente:ruta.npz"``) o archivos de bot (``"bots/mi_bot.py"``); por defecto,
    :func:`participantes_por_defecto`. ``procesos`` reparte las partidas entre varios núcleos
    (0 = todos). ``al_progreso(hechas, total)`` se llama al terminar cada trozo.
    """
    participantes = list(participantes or participantes_por_defecto())
    if len(set(participantes)) != len(participantes) or len(participantes) < 2:
        raise ValueError("Hacen falta al menos 2 participantes distintos")
    for p in participantes:
        fabrica(p)  # comprueba que todos son válidos antes de empezar
    partidas_por_cruce = max(2, partidas_por_cruce // 2 * 2)
    procesos = procesos or os.cpu_count() or 1

    tareas = []
    for k, (a, b) in enumerate(itertools.combinations(participantes, 2)):
        for t, inicio in enumerate(range(0, partidas_por_cruce, _TROZO)):
            n = min(_TROZO, partidas_por_cruce - inicio)
            tareas.append((a, b, n, mejor_de, seed * 1_000_003 + k * 1_009 + t))
    total = sum(t[2] for t in tareas)

    resultado = ResultadoTorneo(participantes, partidas_por_cruce, mejor_de, seed,
                                fecha=datetime.now().isoformat(timespec="seconds"))
    inicio_reloj = time.perf_counter()
    hechas = 0

    def anotar(a: str, b: str, r: ResultadoArena) -> None:
        nonlocal hechas
        v, n = resultado.cruces.get((a, b), (0, 0))
        resultado.cruces[(a, b)] = (v + r.victorias_a, n + r.partidas)
        hechas += r.partidas
        if al_progreso is not None:
            al_progreso(hechas, total)

    if procesos == 1:
        for tarea in tareas:
            anotar(*_trozo(tarea))
    else:
        with ProcessPoolExecutor(procesos) as ex:
            for futuro in as_completed([ex.submit(_trozo, t) for t in tareas]):
                anotar(*futuro.result())
    resultado.cruces = dict(sorted(
        resultado.cruces.items(),
        key=lambda kv: (participantes.index(kv[0][0]), participantes.index(kv[0][1]))))
    resultado.segundos = time.perf_counter() - inicio_reloj
    return resultado


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mus-torneo",
                                     description="Torneo de bots todos contra todos.")
    parser.add_argument("--participantes",
                        help="separados por comas (por defecto, todos los bots y los de bots/)")
    parser.add_argument("--bots", default="bots", help="carpeta con bots externos (.py)")
    parser.add_argument("-n", "--partidas", type=int, default=200, help="partidas por cruce")
    parser.add_argument("--mejor-de", type=int, choices=(3, 5), default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-p", "--procesos", type=int, default=0,
                        help="procesos en paralelo (0 = todos los núcleos)")
    parser.add_argument("--json", help="guardar el resultado completo en este archivo JSON")
    parser.add_argument("--markdown", help="guardar la clasificación en este archivo Markdown")
    args = parser.parse_args(argv)

    participantes = ([p.strip() for p in args.participantes.split(",")] if args.participantes
                     else participantes_por_defecto(args.bots))
    print(f"Torneo: {len(participantes)} participantes, {args.partidas} partidas por cruce.")

    ultimo = [-1]

    def progreso(hechas: int, total: int) -> None:
        porcentaje = 100 * hechas // total
        if porcentaje // 10 != ultimo[0]:
            ultimo[0] = porcentaje // 10
            print(f"  {porcentaje:3d} % ({hechas}/{total} partidas)", flush=True)

    resultado = jugar_torneo(participantes, args.partidas, args.mejor_de, args.seed,
                             args.procesos, progreso)
    print()
    print(resultado)
    print(f"\n({resultado.segundos:.0f} s)")
    if args.json:
        Path(args.json).write_text(json.dumps(resultado.a_dict(), ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(resultado.a_markdown(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

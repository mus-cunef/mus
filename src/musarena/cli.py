"""Comando ``mus-play``: partida de mus en la terminal, con humanos y bots en cualquier asiento.

Ejemplos::

    mus-play                                     # pregunta quién juega en cada asiento
    mus-play --jugadores humano,reglas,reglas,reglas
    mus-play --jugadores humano,reglas:agresivo,reglas,reglas:conservador
    mus-play --jugadores reglas,random,reglas,random --mejor-de 5    # solo bots, a mirar

Si juega algún humano, la partida se guarda en ``partidas/`` (ver :mod:`musarena.grabacion`),
también si se interrumpe a medias. ``--no-grabar`` lo desactiva.
"""

from __future__ import annotations

import argparse
import random
from collections.abc import Callable, Sequence

from musarena.grabacion import CARPETA_POR_DEFECTO, Grabador
from musarena.match import Match
from musarena.player import Player
from musarena.players import OPCIONES, HumanTerminalPlayer, crear_jugador, es_tipo_valido
from musarena.players.human_terminal import lineas_resumen
from musarena.state import nombre_jugador, nombre_pareja


def preguntar_mejor_de(entrada: Callable[[str], str] = input) -> int:
    """Pregunta si la partida es al mejor de 3 o de 5 vacas hasta recibir una respuesta válida."""
    while True:
        respuesta = entrada("¿Partida al mejor de 3 o de 5 vacas? [3/5]: ").strip()
        if respuesta in ("3", "5"):
            return int(respuesta)
        print("Responde 3 o 5.")


def preguntar_jugadores(entrada: Callable[[str], str] = input) -> list[str]:
    """Pregunta qué tipo de jugador ocupa cada asiento (por defecto, humano)."""
    print(f"¿Quién juega en cada asiento? Opciones: {', '.join(OPCIONES)}.")
    tipos = []
    for asiento in range(4):
        while True:
            respuesta = entrada(f"  {nombre_jugador(asiento)} [humano]: ").strip().lower()
            respuesta = respuesta or "humano"
            if es_tipo_valido(respuesta):
                tipos.append(respuesta)
                break
            print(f"  Escribe una de estas opciones: {', '.join(OPCIONES)}.")
    return tipos


def crear_mesa(tipos: Sequence[str], seed: int | None = None) -> list[Player]:
    """Crea los cuatro jugadores. Si hay varios humanos, se avisa de cada turno y se hace pausa."""
    if len(tipos) != 4:
        raise ValueError("Hacen falta 4 jugadores")
    humanos = [a for a, t in enumerate(tipos) if t == "humano"]
    jugadores: list[Player] = []
    for asiento, tipo in enumerate(tipos):
        nombre = nombre_jugador(asiento)
        if tipo == "humano":
            jugadores.append(HumanTerminalPlayer(
                nombre=nombre,
                pausa_entre_turnos=len(humanos) > 1,
                mostrar_resumenes=asiento == humanos[0],  # un solo resumen por mano
            ))
        else:
            semilla = None if seed is None else seed * 4 + asiento
            jugadores.append(crear_jugador(tipo, nombre=f"{nombre} ({tipo})", seed=semilla))
    return jugadores


def jugar(match: Match, hay_humanos: bool) -> int:
    """Juega la partida. Si solo hay bots, enseña el resumen de cada mano para poder seguirla."""
    if hay_humanos:
        return match.play()
    while not match.terminada:
        manos = len(match.state.manos_jugadas)
        match.step()
        if len(match.state.manos_jugadas) > manos:
            for linea in lineas_resumen(match.state.manos_jugadas[-1], tuple(match.state.vacas)):
                print(linea)
    return match.ganador


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mus-play", description="Juega al mus en la terminal.")
    parser.add_argument("--mejor-de", type=int, choices=(3, 5), help="vacas de la partida")
    parser.add_argument("--jugadores", help=f"4 tipos separados por comas ({', '.join(OPCIONES)})")
    parser.add_argument("--seed", type=int, default=None, help="semilla para repetir la partida")
    parser.add_argument("--no-grabar", action="store_true",
                        help="no guardar la partida (se guarda si juega algún humano)")
    parser.add_argument("--carpeta-partidas", default=str(CARPETA_POR_DEFECTO),
                        help="dónde se guardan las partidas")
    args = parser.parse_args(argv)

    tipos = None
    if args.jugadores:
        tipos = [t.strip().lower() for t in args.jugadores.split(",")]
        if len(tipos) != 4 or not all(es_tipo_valido(t) for t in tipos):
            parser.error(f"--jugadores necesita 4 tipos de entre: {', '.join(OPCIONES)}")

    print("Mus Arena · 4 jugadores, pareja A (jugadores 1 y 3) contra B (jugadores 2 y 4).")
    print("En cualquier momento puedes escribir '/chat mensaje' para hablar con la mesa.")
    match = grabador = None
    try:
        mejor_de = args.mejor_de or preguntar_mejor_de()
        tipos = tipos or preguntar_jugadores()
        # La semilla del reparto se apunta siempre, para poder repetir y grabar la partida.
        seed = args.seed if args.seed is not None else random.randrange(2**32)
        if "humano" in tipos and not args.no_grabar:
            grabador = Grabador(seed, mejor_de, tipos)
        match = Match(crear_mesa(tipos, args.seed), mejor_de=mejor_de, seed=seed,
                      al_decidir=grabador)
        ganador = jugar(match, hay_humanos="humano" in tipos)
    except (KeyboardInterrupt, EOFError):
        print("\nPartida interrumpida.")
        return 1
    finally:
        if grabador is not None and match is not None and grabador.partida.acciones:
            print(f"Partida guardada en {grabador.guardar(match, args.carpeta_partidas)}")
    vacas = match.state.vacas
    print(f"Resultado: pareja {nombre_pareja(ganador)} gana {vacas[ganador]}-{vacas[1 - ganador]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

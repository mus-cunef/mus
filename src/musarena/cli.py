"""Comando ``mus-play``: partida de mus en la terminal con los cuatro asientos humanos."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from musarena.match import Match
from musarena.players import HumanTerminalPlayer
from musarena.state import nombre_jugador, nombre_pareja


def preguntar_mejor_de(entrada: Callable[[str], str] = input) -> int:
    """Pregunta si la partida es al mejor de 3 o de 5 vacas hasta recibir una respuesta válida."""
    while True:
        respuesta = entrada("¿Partida al mejor de 3 o de 5 vacas? [3/5]: ").strip()
        if respuesta in ("3", "5"):
            return int(respuesta)
        print("Responde 3 o 5.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mus-play", description="Juega al mus en la terminal.")
    parser.add_argument("--mejor-de", type=int, choices=(3, 5), help="vacas de la partida")
    parser.add_argument("--seed", type=int, default=None, help="semilla para repetir el reparto")
    args = parser.parse_args(argv)

    print("Mus Arena · 4 jugadores, pareja A (jugadores 1 y 3) contra B (jugadores 2 y 4).")
    print("En cualquier momento puedes escribir '/chat mensaje' para hablar con la mesa.")
    try:
        mejor_de = args.mejor_de or preguntar_mejor_de()
        jugadores = [
            HumanTerminalPlayer(
                nombre=nombre_jugador(asiento),
                pausa_entre_turnos=True,
                mostrar_resumenes=(asiento == 0),  # un solo resumen por mano en la pantalla
            )
            for asiento in range(4)
        ]
        match = Match(jugadores, mejor_de=mejor_de, seed=args.seed)
        ganador = match.play()
    except (KeyboardInterrupt, EOFError):
        print("\nPartida interrumpida.")
        return 1
    vacas = match.state.vacas
    print(f"Resultado: pareja {nombre_pareja(ganador)} gana {vacas[ganador]}-{vacas[1 - ganador]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

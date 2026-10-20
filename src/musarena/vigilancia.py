"""Vigilancia de bots: un bot que falla, se cuelga o juega ilegal pierde la partida.

En el torneo y en la arena cada jugador puede ir envuelto en un :class:`JugadorVigilado`, que
en cada decisión comprueba tres cosas:

- **que no falle**: si el bot lanza una excepción, comete una falta;
- **que juegue legal**: si devuelve una acción que no está entre las legales, comete una falta
  (antes de que el motor la rechace);
- **que responda a tiempo**: si tarda más de ``limite_segundos``, comete una falta. Para poder
  cortar a un bot colgado, su decisión se calcula en un hilo aparte; si no termina a tiempo,
  ese hilo se abandona (es un hilo *daemon*, así que no impide que el programa acabe).

Una falta lanza :class:`FaltaDeBot` con el asiento y el motivo. Quien juega la partida (la
arena) la captura y da la partida por perdida a la pareja de ese bot, **sin romper el torneo**.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Sequence

from musarena.actions import Action
from musarena.chat import CanalChat
from musarena.observation import Observation
from musarena.player import Player


class FaltaDeBot(Exception):
    """Un bot ha fallado, se ha colgado o ha jugado ilegal."""

    def __init__(self, asiento: int | None, motivo: str) -> None:
        super().__init__(motivo)
        self.asiento = asiento
        self.motivo = motivo


class _Hilo:
    """Un hilo propio que ejecuta las llamadas del bot, para poder esperarlas con límite."""

    def __init__(self) -> None:
        self._pedidos: queue.Queue = queue.Queue()
        self._respuestas: queue.Queue = queue.Queue()
        threading.Thread(target=self._bucle, daemon=True).start()

    def _bucle(self) -> None:
        while True:
            funcion, args = self._pedidos.get()
            try:
                self._respuestas.put((True, funcion(*args)))
            except BaseException as e:  # también SystemExit: el bot no puede tumbar el hilo
                self._respuestas.put((False, e))

    def llamar(self, funcion: Callable, args: tuple, limite: float) -> object:
        self._pedidos.put((funcion, args))
        try:
            correcto, valor = self._respuestas.get(timeout=limite)
        except queue.Empty:
            raise TimeoutError from None
        if not correcto:
            raise valor
        return valor


class JugadorVigilado(Player):
    """Envuelve a un jugador y convierte cualquier problema suyo en una :class:`FaltaDeBot`."""

    def __init__(self, jugador: Player, limite_segundos: float | None = 5.0) -> None:
        super().__init__(jugador.nombre)
        self.jugador = jugador
        self.limite = limite_segundos
        self._hilo = _Hilo() if limite_segundos else None
        self.colgado = False

    def sit(self, asiento: int, chat: CanalChat) -> None:
        super().sit(asiento, chat)
        self._llamar(self.jugador.sit, asiento, chat)

    def _llamar(self, funcion: Callable, *args: object) -> object:
        if self.colgado:
            raise FaltaDeBot(self.asiento, "sigue colgado de una jugada anterior")
        try:
            if self._hilo is None:
                return funcion(*args)
            return self._hilo.llamar(funcion, args, self.limite)
        except TimeoutError:
            self.colgado = True
            raise FaltaDeBot(self.asiento, f"no ha respondido en {self.limite:g} s") from None
        except FaltaDeBot:
            raise
        except BaseException as e:
            raise FaltaDeBot(self.asiento, f"error: {type(e).__name__}: {e}") from e

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        accion = self._llamar(self.jugador.choose_action, observation, legal_actions)
        if accion not in legal_actions:
            raise FaltaDeBot(self.asiento, f"jugada ilegal: {accion!r}")
        return accion

    def on_hand_end(self, observation: Observation) -> None:
        self._llamar(self.jugador.on_hand_end, observation)

    def on_game_end(self, observation: Observation) -> None:
        try:
            self._llamar(self.jugador.on_game_end, observation)
        except FaltaDeBot:
            pass  # la partida ya ha terminado: un fallo aquí no cambia el resultado


def vigilar(crear: Callable[[int], Player],
            limite_segundos: float | None) -> Callable[[int], Player]:
    """Fábrica de jugadores vigilados. Si el bot falla al crearse, también es una falta."""

    def crear_vigilado(seed: int) -> Player:
        try:
            jugador = crear(seed)
        except Exception as e:
            raise FaltaDeBot(None, f"error al crear el bot: {type(e).__name__}: {e}") from e
        return JugadorVigilado(jugador, limite_segundos)

    return crear_vigilado

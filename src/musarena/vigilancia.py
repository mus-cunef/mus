"""Vigilancia de bots: un bot que falla, se cuelga o juega ilegal pierde la partida.

En el torneo y en la arena cada bot juega envuelto en un :class:`JugadorVigilado`, que en cada
decisión comprueba tres cosas:

- **que no falle**: si el bot lanza una excepción (también ``SystemExit``), comete una falta;
- **que juegue legal**: si devuelve algo que no es una de las acciones legales (de la misma
  clase y con los mismos datos, ver :func:`~musarena.engine.buscar_legal`), comete una falta;
- **que responda a tiempo**: si tarda más de ``limite_segundos``, comete una falta.

Para que ningún bot pueda romper el torneo, **cada pareja de bots vive en su propio proceso**
(una :class:`Caja`). El bot nunca toca la partida: recibe copias de su observación y de las
acciones legales, y solo devuelve *qué número* de acción legal elige. Si se cuelga, su proceso
se mata (no se queda gastando CPU ni hace perder por tiempo a los demás); si el proceso muere
(``os._exit``, un fallo grave), solo pierde esa partida y para la siguiente se arranca otro.
Crear el bot (importar su archivo incluido) también tiene límite de tiempo.

Las cajas se reutilizan partida tras partida, porque arrancar un proceso cuesta casi un segundo.
Una falta lanza :class:`FaltaDeBot` con el asiento y el motivo. Quien juega la partida (la
arena) la captura y da la partida por perdida a la pareja de ese bot, **sin romper el torneo**.
"""

from __future__ import annotations

import multiprocessing
import os
import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from multiprocessing.connection import Connection

from musarena.actions import Action
from musarena.chat import LONGITUD_MAXIMA, CanalChat, MensajeChat
from musarena.engine import buscar_legal
from musarena.observation import Observation
from musarena.player import Player

#: Segundos para arrancar un proceso nuevo (solo nuestro código, el bot aún no ha hecho nada).
LIMITE_ARRANQUE = 120.0
#: Crear el bot (importar su archivo, cargar un modelo) puede tardar más que una jugada.
FACTOR_CREAR = 6
#: Y nunca menos de esto (con un equipo cargado, crear un bot puede tardar más de un segundo).
MINIMO_CREAR = 5.0
#: Mensajes de chat que un bot puede escribir en cada llamada.
MAX_MENSAJES = 5

#: Crea un bot a partir de una semilla. Tiene que poder enviarse a otro proceso (no lambdas).
Receta = Callable[[int], Player]


class FaltaDeBot(Exception):
    """Un bot ha fallado, se ha colgado o ha jugado ilegal."""

    def __init__(self, asiento: int | None, motivo: str) -> None:
        super().__init__(motivo)
        self.asiento = asiento
        self.motivo = motivo


class _ProcesoTerminado(Exception):
    """El proceso de la caja ha muerto a mitad de una llamada (por culpa del bot)."""


# --- Lo que corre dentro del proceso hijo -----------------------------------------------------


def _texto(objeto: object) -> str:
    """``repr`` que no puede fallar (el ``__repr__`` del bot puede lanzar una excepción)."""
    try:
        return repr(objeto)[:200]
    except BaseException:
        return f"<{type(objeto).__name__} sin repr>"


def _error(e: BaseException) -> str:
    try:
        return f"{type(e).__name__}: {e}"[:300]
    except BaseException:
        return type(e).__name__


class _ChatDelBot:
    """El chat que ve el bot en su proceso: lee el de su observación y lo que escribe se manda
    a la mesa al terminar la llamada."""

    def __init__(self, asiento: int) -> None:
        self.asiento = asiento
        self.mensajes: tuple[MensajeChat, ...] = ()
        self.pendientes: list[str] = []

    def escribir(self, texto: str) -> None:
        if len(self.pendientes) < MAX_MENSAJES:
            self.pendientes.append(str(texto)[:LONGITUD_MAXIMA])


class _Hueco:
    """Un bot dentro del proceso hijo, con su chat y las manos jugadas que ya ha recibido."""

    def __init__(self, bot: Player) -> None:
        self.bot = bot
        self.chat: _ChatDelBot | None = None
        self.manos: tuple = ()

    def observacion(self, ligera: Observation, desde: int) -> Observation:
        """Reconstruye la observación completa: solo llegan las manos jugadas nuevas."""
        self.manos = self.manos[:desde] + ligera.manos_jugadas
        if self.chat is not None:
            self.chat.mensajes = ligera.chat
        return replace(ligera, manos_jugadas=self.manos)


def _atender(huecos: dict[int, _Hueco], orden: str, hueco: int, args: tuple) -> object:
    if orden == "crear":
        receta, seed = args
        huecos.pop(hueco, None)
        huecos[hueco] = _Hueco(receta(seed))
        return str(huecos[hueco].bot.nombre)
    h = huecos[hueco]
    if orden == "sit":
        h.chat = _ChatDelBot(args[0])
        h.bot.sit(args[0], h.chat)  # type: ignore[arg-type]
        return None
    observacion = h.observacion(*args[:2])
    if orden == "decidir":
        legales = args[2]
        accion = h.bot.choose_action(observacion, list(legales))
        legal = buscar_legal(legales, accion)
        if legal is None:
            return _texto(accion)  # jugada ilegal: se devuelve cómo era, para el motivo
        return next(i for i, a in enumerate(legales) if a is legal)
    if orden == "fin_mano":
        return h.bot.on_hand_end(observacion)
    return h.bot.on_game_end(observacion)


def _servir(conexion: Connection) -> None:
    """Bucle del proceso hijo: atiende las llamadas a sus bots hasta que se cierra la tubería."""
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"  # cuentas pequeñas; con un hilo por núcleo no cabrían
    import musarena.players  # noqa: F401  (se carga ya, fuera del tiempo del bot)

    huecos: dict[int, _Hueco] = {}
    conexion.send("listo")
    while True:
        try:
            orden, hueco, args = conexion.recv()
        except EOFError:
            return
        except BaseException as e:  # p. ej. la receta no se puede reconstruir aquí
            conexion.send(((False, _error(e)), []))
            continue
        try:
            respuesta = (True, _atender(huecos, orden, hueco, args))
        except BaseException as e:  # también SystemExit: el bot no puede tumbar el proceso
            respuesta = (False, _error(e))
        chat = huecos[hueco].chat if hueco in huecos else None
        textos = chat.pendientes if chat is not None else []
        if chat is not None:
            chat.pendientes = []
        conexion.send((respuesta, textos))


# --- Lo que corre en el proceso de la partida ---------------------------------------------------


class Caja:
    """Un proceso hijo donde juegan los bots de una pareja. Si se cuelga o muere, se mata, y
    la siguiente llamada arranca otro."""

    def __init__(self) -> None:
        self._proceso: multiprocessing.process.BaseProcess | None = None
        self._conexion: Connection | None = None

    def _arrancar(self) -> None:
        """Arranca el proceso. Si no arranca, la culpa no es del bot: es un error de verdad."""
        contexto = multiprocessing.get_context("spawn")  # igual en Windows y en Linux
        nuestra, suya = contexto.Pipe()
        self._proceso = contexto.Process(target=_servir, args=(suya,), daemon=True)
        self._proceso.start()
        suya.close()
        self._conexion = nuestra
        try:
            if nuestra.poll(LIMITE_ARRANQUE) and nuestra.recv() == "listo":
                return
        except (EOFError, OSError):
            pass
        self._proceso.join(1)
        codigo = self._proceso.exitcode
        self.cerrar()
        raise RuntimeError(f"No arranca el proceso de un bot (código {codigo})")

    def llamar(self, orden: str, hueco: int, args: tuple,
               limite: float | None) -> tuple[tuple[bool, object], list[str]]:
        """Manda una llamada al bot ``hueco`` y espera, como mucho ``limite`` segundos."""
        if self._proceso is None:
            self._arrancar()
        try:
            self._conexion.send((orden, hueco, args))
            a_tiempo = limite is None or self._conexion.poll(limite)
            if a_tiempo:
                return self._conexion.recv()
        except (EOFError, OSError) as e:  # el proceso ha muerto (os._exit, memoria...)
            codigo = None
            if self._proceso is not None:
                self._proceso.join(1)
                codigo = self._proceso.exitcode
            self.cerrar()
            raise _ProcesoTerminado(f"código {codigo}") from e
        self.cerrar()  # colgado: se mata y no sigue gastando CPU
        raise TimeoutError

    def cerrar(self) -> None:
        if self._proceso is None:
            return
        self._conexion.close()
        self._proceso.kill()
        self._proceso.join()
        self._proceso = self._conexion = None


_libres: list[Caja] = []
_cerrojo = threading.Lock()


def tomar_caja() -> Caja:
    """Una caja sin usar (con su proceso ya arrancado si se ha usado antes)."""
    with _cerrojo:
        return _libres.pop() if _libres else Caja()


def devolver_caja(caja: Caja) -> None:
    with _cerrojo:
        _libres.append(caja)


def cerrar_cajas() -> None:
    """Cierra los procesos que esperan sin usar (al acabar un torneo, para liberar memoria)."""
    with _cerrojo:
        cajas = list(_libres)
        _libres.clear()
    for caja in cajas:
        caja.cerrar()


class JugadorVigilado(Player):
    """Un bot que vive en una :class:`Caja`: cualquier problema suyo es una :class:`FaltaDeBot`.

    Se crea con su receta y su semilla; si el bot falla o tarda demasiado al crearse, también
    es una falta (con ``asiento=None``, porque aún no está sentado).
    """

    def __init__(self, caja: Caja, hueco: int, receta: Receta, seed: int,
                 limite_segundos: float | None = 5.0) -> None:
        super().__init__("bot")
        self._caja = caja
        self._hueco = hueco
        self._manos_enviadas = 0
        self.limite = limite_segundos
        limite_crear = (None if limite_segundos is None
                        else max(limite_segundos * FACTOR_CREAR, MINIMO_CREAR))
        self.nombre = str(self._llamar("crear", (receta, seed), limite_crear,
                                       "error al crear el bot"))

    def _llamar(self, orden: str, args: tuple, limite: float | None,
                prefijo: str = "error") -> object:
        try:
            (correcto, valor), textos = self._caja.llamar(orden, self._hueco, args, limite)
        except TimeoutError:
            raise FaltaDeBot(self.asiento, f"no ha respondido en {limite:g} s") from None
        except _ProcesoTerminado as e:
            raise FaltaDeBot(self.asiento, f"su proceso ha terminado ({e})") from None
        for texto in textos:
            self.say(texto)
        if not correcto:
            raise FaltaDeBot(self.asiento, f"{prefijo}: {valor}")
        return valor

    def _ligera(self, observation: Observation) -> tuple[Observation, int]:
        """La observación con solo las manos jugadas que el bot aún no tiene, y desde cuál van.

        ``manos_jugadas`` solo crece y al final de la partida es casi todo lo que ocupa; mandarla
        entera en cada jugada haría la vigilancia varias veces más lenta.
        """
        desde = min(self._manos_enviadas, len(observation.manos_jugadas))
        self._manos_enviadas = len(observation.manos_jugadas)
        return replace(observation, manos_jugadas=observation.manos_jugadas[desde:]), desde

    def sit(self, asiento: int, chat: CanalChat) -> None:
        super().sit(asiento, chat)
        self._llamar("sit", (asiento,), self.limite)

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        valor = self._llamar("decidir", (*self._ligera(observation), tuple(legal_actions)),
                             self.limite)
        if not isinstance(valor, int) or not 0 <= valor < len(legal_actions):
            raise FaltaDeBot(self.asiento, f"jugada ilegal: {valor}")
        return legal_actions[valor]

    def on_hand_end(self, observation: Observation) -> None:
        self._llamar("fin_mano", self._ligera(observation), self.limite)

    def on_game_end(self, observation: Observation) -> None:
        try:
            self._llamar("fin_partida", self._ligera(observation), self.limite)
        except FaltaDeBot:
            pass  # la partida ya ha terminado: un fallo aquí no cambia el resultado

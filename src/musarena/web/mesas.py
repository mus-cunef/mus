"""Mesas de la web: partidas con humanos (cada uno desde su navegador) y bots.

Cómo avanza una partida:

- Cuando le toca a un **bot**, la mesa juega por él, pero como mucho una jugada cada
  ``pausa_bots`` segundos, para que en la pantalla se vea lo que hace. No hay hilos: la mesa
  avanza cada vez que alguien pregunta por ella (los navegadores preguntan cada medio segundo).
- Cuando le toca a un **humano**, la mesa espera a que su navegador mande la jugada.
  :meth:`Mesa.jugar` comprueba que es su turno, que la jugada es una de las legales y que
  corresponde a la situación que veía (``version``); si no, la rechaza sin tocar nada.

Seguridad: cada asiento humano tiene un **código secreto** (``token``). Quien no lo tiene no
puede ver ese asiento ni jugar por él, y la vista de un asiento solo contiene su observación.

Las mesas de los torneos privados se guardan en la base de datos jugada a jugada
(``al_cambiar``). Si el servidor se reinicia, :class:`GestorMesas` las reconstruye con
``restaurador``: la misma semilla y las mismas jugadas dan exactamente la misma partida.
"""

from __future__ import annotations

import random
import secrets
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from musarena.actions import Action
from musarena.arena import fabrica
from musarena.engine import legal_actions
from musarena.grabacion import Grabador, accion_desde_dict
from musarena.match import Match
from musarena.observation import Observation
from musarena.player import Player
from musarena.players import BOTS, OPCIONES
from musarena.players.externos import buscar_bots, es_bot_externo, nombre_externo
from musarena.state import nombre_jugador
from musarena.web.config import Config
from musarena.web.vista import vista

HUMANO = "humano"

#: Longitud máxima del nombre que se pone un humano.
MAX_NOMBRE = 20


def limpiar_nombre(nombre: object) -> str | None:
    """Nombre de un humano listo para enseñar: sin caracteres de control ni espacios de más,
    y como mucho :data:`MAX_NOMBRE` letras. Vacío -> ``None`` (se usa "Jugador N")."""
    if not isinstance(nombre, str):
        return None
    limpio = " ".join("".join(c for c in nombre if c.isprintable()).split())[:MAX_NOMBRE].strip()
    return limpio or None

#: Velocidad de los bots: multiplica la pausa entre jugadas (``Config.pausa_bots``). Por defecto
#: "normal" (0,6 s por jugada): con menos, la gente no llega a ver qué ha hecho cada bot.
VELOCIDADES: dict[str, float] = {"rapida": 0.5, "normal": 1.0, "lenta": 2.0}


class ErrorMesa(Exception):
    """Petición rechazada; ``codigo`` es el código HTTP con el que se responde."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


class JugadorWeb(Player):
    """Un humano en la web: juega la acción que ha mandado su navegador."""

    def __init__(self, nombre: str) -> None:
        super().__init__(nombre)
        self.pendiente: Action | None = None

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        accion, self.pendiente = self.pendiente, None
        if accion is None:
            raise RuntimeError("Le toca a un humano y su navegador no ha mandado ninguna jugada")
        return accion


def tipos_permitidos(config: Config) -> list[str]:
    """Lo que se puede poner en un asiento desde la web: humano, los bots del registro (con
    estilos) y los bots de la carpeta del servidor. Nunca una ruta que mande el usuario."""
    return [HUMANO, *(o for o in OPCIONES if o.partition(":")[0] in BOTS),
            *buscar_bots(config.carpeta_bots)]


def etiqueta(tipo: str) -> str:
    return nombre_externo(tipo) if es_bot_externo(tipo) else tipo


@dataclass
class Mesa:
    tipos: list[str]
    mejor_de: int
    config: Config
    reloj: Callable[[], float] = time.monotonic
    velocidad: str = "normal"
    nombres: Sequence[str | None] = ()  # el nombre de cada humano (opcional)
    id: str = field(default_factory=lambda: secrets.token_urlsafe(9))
    seed: int = field(default_factory=lambda: random.SystemRandom().randrange(2**32))
    #: Códigos de asiento ya decididos (al reconstruir una mesa de torneo).
    tokens_iniciales: dict[int, str] = field(default_factory=dict)
    #: Se llama tras cada jugada (los torneos privados la guardan en la base de datos).
    al_cambiar: Callable[[Mesa], None] | None = None

    def __post_init__(self) -> None:
        if len(self.tipos) != 4:
            raise ErrorMesa("Hacen falta 4 asientos")
        if self.mejor_de not in (3, 5):
            raise ErrorMesa("La partida es al mejor de 3 o de 5 vacas")
        if self.velocidad not in VELOCIDADES:
            raise ErrorMesa(f"Velocidad no válida: {self.velocidad!r}")
        self.pausa = self.config.pausa_bots * VELOCIDADES[self.velocidad]
        if HUMANO not in self.tipos:
            raise ErrorMesa("Tiene que jugar al menos un humano")
        permitidos = set(tipos_permitidos(self.config))
        for t in self.tipos:
            if t not in permitidos:
                raise ErrorMesa(f"Tipo de jugador no permitido: {t!r}")
        nombres = list(self.nombres) + [None] * (4 - len(self.nombres))
        #: Cómo se ve cada asiento: el nombre que se ha puesto un humano o "Jugador N".
        self.apodos = [
            (limpiar_nombre(nombres[a]) if t == HUMANO else None) or nombre_jugador(a)
            for a, t in enumerate(self.tipos)]
        semillas = random.Random(self.seed)
        self.jugadores: list[Player] = []
        self.tokens: dict[int, str] = {}
        for asiento, tipo in enumerate(self.tipos):
            if tipo == HUMANO:
                self.jugadores.append(JugadorWeb(self.apodos[asiento]))
                self.tokens[asiento] = (self.tokens_iniciales.get(asiento)
                                        or secrets.token_urlsafe(16))
            else:
                self.jugadores.append(fabrica(tipo)(semillas.randrange(2**32)))
        # Siempre se apuntan las jugadas (los torneos las necesitan); el archivo solo se escribe
        # si hay carpeta de partidas.
        self.grabador = Grabador(self.seed, self.mejor_de, self.tipos)
        self.match = Match(self.jugadores, mejor_de=self.mejor_de, seed=self.seed,
                           al_decidir=self.grabador)
        self.version = 0
        self.grabada = False
        self.lock = threading.Lock()
        self.ultima_actividad = self.reloj()
        self.proxima_jugada_bot = self.reloj() + self.pausa

    # --- Quién es quién -------------------------------------------------------------------

    def asiento_de(self, token: str) -> int:
        for asiento, propio in self.tokens.items():
            if secrets.compare_digest(propio, token or ""):
                return asiento
        raise ErrorMesa("Código de asiento no válido", 403)

    def jugadores_publicos(self) -> list[dict]:
        """Qué hay en cada asiento (información pública: quién es humano y qué bot es)."""
        return [{"asiento": a, "nombre": self.apodos[a], "humano": t == HUMANO,
                 "tipo": etiqueta(t)} for a, t in enumerate(self.tipos)]

    # --- Avanzar la partida ---------------------------------------------------------------

    def _le_toca_a_un_bot(self) -> bool:
        return not self.match.terminada and self.tipos[self.match.state.turno] != HUMANO

    @property
    def acciones(self) -> list[tuple[int, dict]]:
        """Las jugadas hechas, como ``(asiento, acción)`` (para guardarlas)."""
        return self.grabador.partida.acciones

    def _despues_de_jugar(self) -> None:
        self.version += 1
        self.proxima_jugada_bot = self.reloj() + self.pausa
        if self.match.terminada and not self.grabada:
            self._grabar()
        if self.al_cambiar is not None:
            self.al_cambiar(self)

    def _grabar(self) -> None:
        if self.config.carpeta_partidas and self.grabador.partida.acciones:
            self.grabador.guardar(self.match, self.config.carpeta_partidas)
        self.grabada = True

    def restaurar(self, acciones: Sequence[tuple[int, dict]]) -> None:
        """Repite unas jugadas ya hechas (al reconstruir la mesa tras un reinicio)."""
        al_cambiar, self.al_cambiar = self.al_cambiar, None  # ya están guardadas
        try:
            with self.lock:
                for asiento, datos in acciones:
                    if self.match.terminada or self.match.state.turno != asiento:
                        raise ValueError("Las jugadas guardadas no cuadran con la partida")
                    jugador = self.jugadores[asiento]
                    if isinstance(jugador, JugadorWeb):
                        jugador.pendiente = accion_desde_dict(datos)
                    self.match.step()
                    self.version += 1
        finally:
            self.al_cambiar = al_cambiar

    def avanzar(self) -> None:
        """Juega por los bots las jugadas que ya tocan según el reloj."""
        with self.lock:
            while self._le_toca_a_un_bot() and self.reloj() >= self.proxima_jugada_bot:
                self.match.step()
                self._despues_de_jugar()
                if self.pausa > 0:
                    break

    def vista(self, token: str) -> dict:
        asiento = self.asiento_de(token)
        self.avanzar()
        with self.lock:
            self.ultima_actividad = self.reloj()
            obs = self.match.observation(asiento)
            legales = legal_actions(self.match.state) if obs.es_mi_turno else []
            return vista(obs, legales, self.jugadores_publicos(), self.version)

    def jugar(self, token: str, accion_id: int, version: int) -> None:
        asiento = self.asiento_de(token)
        with self.lock:
            self.ultima_actividad = self.reloj()
            if self.match.terminada:
                raise ErrorMesa("La partida ha terminado", 409)
            if version != self.version:
                raise ErrorMesa("La mesa ha cambiado desde que la viste: vuelve a mirar", 409)
            if self.match.state.turno != asiento:
                raise ErrorMesa("No es tu turno", 409)
            legales = legal_actions(self.match.state)
            if not 0 <= accion_id < len(legales):
                raise ErrorMesa("Jugada no válida")
            self.jugadores[asiento].pendiente = legales[accion_id]
            self.match.step()  # el motor la vuelve a validar
            self._despues_de_jugar()

    def escribir(self, token: str, texto: str) -> None:
        asiento = self.asiento_de(token)
        texto = str(texto)[: self.config.max_chat]
        with self.lock:
            self.ultima_actividad = self.reloj()
            if self.match.chat.escribir(asiento, texto) is not None:
                self.version += 1

    def cerrar(self) -> None:
        """Al cerrar una mesa sin terminar, se graba lo jugado."""
        with self.lock:
            if not self.grabada:
                self._grabar()


class GestorMesas:
    """Todas las mesas abiertas del servidor, con su límite y su caducidad."""

    def __init__(self, config: Config, reloj: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.reloj = reloj
        self._mesas: dict[str, Mesa] = {}
        self._lock = threading.Lock()
        #: Reconstruye una mesa que ya no está en memoria (las de los torneos privados).
        self.restaurador: Callable[[str], Mesa | None] | None = None

    def crear(self, tipos: Sequence[str], mejor_de: int = 3, velocidad: str = "normal",
              nombres: Sequence[str | None] = ()) -> Mesa:
        self.limpiar()
        with self._lock:
            if len(self._mesas) >= self.config.max_mesas:
                raise ErrorMesa("Hay demasiadas mesas abiertas; prueba dentro de un rato", 503)
            mesa = Mesa(list(tipos), mejor_de, self.config, self.reloj, velocidad, nombres)
            self._mesas[mesa.id] = mesa
            return mesa

    def obtener(self, mesa_id: str) -> Mesa:
        mesa = self._mesas.get(mesa_id)
        if mesa is None and self.restaurador is not None:
            with self._lock:
                mesa = self._mesas.get(mesa_id)  # quizá la ha reconstruido otra petición
                if mesa is None:
                    mesa = self.restaurador(mesa_id)
                    if mesa is not None:
                        self._mesas[mesa.id] = mesa
        if mesa is None:
            raise ErrorMesa("La mesa no existe o se ha cerrado por inactividad", 404)
        return mesa

    def poner(self, mesa: Mesa) -> Mesa:
        """Añade una mesa creada fuera (las de los torneos privados no cuentan en el límite)."""
        self.limpiar()
        with self._lock:
            return self._mesas.setdefault(mesa.id, mesa)

    def quitar(self, mesa_id: str) -> None:
        with self._lock:
            self._mesas.pop(mesa_id, None)

    def limpiar(self) -> None:
        """Cierra las mesas sin actividad (y graba lo que tuvieran jugado)."""
        limite = self.reloj() - 60 * self.config.minutos_inactiva
        with self._lock:
            viejas = [m for m in self._mesas.values() if m.ultima_actividad < limite]
            for mesa in viejas:
                del self._mesas[mesa.id]
        for mesa in viejas:
            mesa.cerrar()

    def __len__(self) -> int:
        return len(self._mesas)

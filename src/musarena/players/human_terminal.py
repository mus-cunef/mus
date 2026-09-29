"""Jugador humano que juega desde la terminal."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from musarena.actions import (
    ENVIDO_MAX,
    ENVIDO_MIN,
    ENVIDO_POR_DEFECTO,
    REENVIDO_MIN,
    Action,
    Descarte,
    Envido,
    Reenvido,
)
from musarena.observation import Observation
from musarena.player import Player
from musarena.state import Fase, ResumenMano, nombre_jugador, nombre_pareja

# Opciones del menú que agrupan varias acciones legales y piden un dato más.
_ENVIDO_N = "envido_n"
_REENVIDO_N = "reenvido_n"
_DESCARTE = "descarte"


def _quien(asiento: int) -> str:
    return f"{nombre_jugador(asiento)} (pareja {nombre_pareja(asiento % 2)})"


def lineas_resumen(resumen: ResumenMano, vacas: tuple[int, int]) -> list[str]:
    """Texto del final de una mano: las cartas de todos, los cobros y el marcador."""
    lineas = ["", f"--- Fin de la mano {resumen.numero} ---"]
    for asiento, cartas in enumerate(resumen.cartas):
        lineas.append(f"  {_quien(asiento)}: {', '.join(str(c) for c in cartas)}")
    for cobro in resumen.cobros:
        lance = f"{cobro.lance}: " if cobro.lance else ""
        lineas.append(
            f"  Pareja {nombre_pareja(cobro.pareja)} cobra {cobro.tantos} ({lance}{cobro.motivo})"
        )
    lineas.append(f"  Tantos: A {resumen.tantos[0]} - B {resumen.tantos[1]}")
    if resumen.ganador_vaca is not None:
        lineas.append(f"  ¡La pareja {nombre_pareja(resumen.ganador_vaca)} gana la vaca!")
    lineas.append(f"  Vacas: A {vacas[0]} - B {vacas[1]}")
    return lineas


def _maximo_reenvido(legal_actions: Sequence[Action]) -> int:
    """Mayor reenvido legal: depende de lo apostado, porque el total no puede pasar de 40."""
    return max(a.tantos for a in legal_actions if isinstance(a, Reenvido))


class HumanTerminalPlayer(Player):
    """Muestra la mesa por pantalla y pide la jugada por número.

    ``entrada`` y ``salida`` se pueden sustituir (por ejemplo en los tests). Con
    ``pausa_entre_turnos`` se avisa de quién es el turno y se espera a que pulse Enter antes de
    enseñar sus cartas, para poder jugar varios humanos en la misma terminal.
    """

    def __init__(
        self,
        nombre: str | None = None,
        entrada: Callable[[str], str] = input,
        salida: Callable[[str], None] = print,
        pausa_entre_turnos: bool = False,
        mostrar_resumenes: bool = True,
    ) -> None:
        super().__init__(nombre)
        self._entrada = entrada
        self._salida = salida
        self.pausa_entre_turnos = pausa_entre_turnos
        self.mostrar_resumenes = mostrar_resumenes
        self._visto: tuple[int, int] = (0, 0)  # (número de mano, eventos ya mostrados)
        self._chat_visto = 0

    # --- API de Player ---------------------------------------------------------------------

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        if self.pausa_entre_turnos:
            self._salida("")
            self._salida("=" * 60)
            self._pedir(f"Turno de {self._quien(observation.asiento)}. Pulsa Enter para jugar...")
            self._salida("\033[2J\033[H")  # limpia la pantalla para no ver las cartas del anterior
        self._mostrar(observation)
        opciones = self._opciones(legal_actions)
        if len(opciones) == 1 and opciones[0][1] == _DESCARTE:
            return self._pedir_descarte(observation, legal_actions)
        for i, (texto, _) in enumerate(opciones, start=1):
            self._salida(f"  {i}. {texto}")
        while True:
            respuesta = self._pedir("Elige una opción (o /chat mensaje): ")
            if respuesta is None:
                continue
            if not (respuesta.isdigit() and 1 <= int(respuesta) <= len(opciones)):
                self._salida(f"Escribe un número entre 1 y {len(opciones)}.")
                continue
            eleccion = opciones[int(respuesta) - 1][1]
            if eleccion == _ENVIDO_N:
                return Envido(self._pedir_cantidad("¿Cuántos tantos envidas?", ENVIDO_MIN,
                                                   ENVIDO_MAX))
            if eleccion == _REENVIDO_N:
                maximo = _maximo_reenvido(legal_actions)
                return Reenvido(self._pedir_cantidad("¿Cuántos tantos más?", REENVIDO_MIN,
                                                     maximo))
            return eleccion

    def on_hand_end(self, observation: Observation) -> None:
        if not self.mostrar_resumenes:
            return
        for linea in lineas_resumen(observation.manos_jugadas[-1], observation.vacas):
            self._salida(linea)

    def on_game_end(self, observation: Observation) -> None:
        if self.mostrar_resumenes and observation.ganador is not None:
            self._salida("")
            self._salida(f"*** La pareja {nombre_pareja(observation.ganador)} gana la partida ***")

    # --- Pantalla --------------------------------------------------------------------------

    @staticmethod
    def _quien(asiento: int) -> str:
        return _quien(asiento)

    def _mostrar(self, obs: Observation) -> None:
        s = self._salida
        vaca = obs.vacas[0] + obs.vacas[1] + 1
        s("")
        s(
            f"Vaca {vaca} · Mano {obs.numero_mano} · Tantos A {obs.tantos[0]} - B {obs.tantos[1]}"
            f" · Vacas A {obs.vacas[0]} - B {obs.vacas[1]} (gana quien llegue a "
            f"{obs.vacas_para_ganar})"
        )
        s(f"Eres el {self._quien(obs.asiento)}; tu compañero es el "
          f"{nombre_jugador(obs.companero)}. Es mano el {nombre_jugador(obs.mano)}.")

        numero, vistos = self._visto
        if numero != obs.numero_mano:
            vistos = 0
        nuevos = obs.historial[vistos:]
        if nuevos:
            s("Lo último que ha pasado:")
            for evento in nuevos:
                quien = f"{nombre_jugador(evento.asiento)}: " if evento.asiento is not None else ""
                s(f"  · {quien}{evento.texto}")
        self._visto = (obs.numero_mano, len(obs.historial))

        mensajes = obs.chat[self._chat_visto:]
        if mensajes:
            s("Chat:")
            for m in mensajes:
                s(f"  {m}")
        self._chat_visto = len(obs.chat)

        if obs.fase is Fase.LANCE and obs.lance is not None:
            s(f"Lance: {obs.lance}")
            ap = obs.apuesta
            if ap is not None and ap.pareja_apostadora is not None:
                cantidad = "ÓRDAGO" if ap.ordago else f"{ap.tantos} tantos"
                s(f"  Apuesta de la pareja {nombre_pareja(ap.pareja_apostadora)}: {cantidad}"
                  f" (si no la queréis, cobran {ap.deje})")
        elif obs.fase is Fase.MUS:
            s("Fase de mus")
        elif obs.fase is Fase.DESCARTE:
            s("Descartes")

        s("Tus cartas:")
        for i, carta in enumerate(obs.cartas, start=1):
            s(f"  [{i}] {carta}")

    # --- Entrada ---------------------------------------------------------------------------

    def _pedir(self, mensaje: str) -> str | None:
        """Lee una línea. Si es ``/chat ...`` la envía al chat y devuelve ``None``."""
        texto = self._entrada(mensaje).strip()
        if texto.lower().startswith("/chat"):
            mensaje_chat = texto[5:].strip()
            if mensaje_chat:
                self.say(mensaje_chat)
                self._salida("(mensaje enviado al chat)")
            else:
                self._salida("Uso: /chat tu mensaje")
            return None
        return texto

    def _pedir_cantidad(self, pregunta: str, minimo: int, maximo: int) -> int:
        while True:
            respuesta = self._pedir(f"{pregunta} ({minimo}-{maximo}): ")
            if respuesta is None:
                continue
            if respuesta.isdigit() and minimo <= int(respuesta) <= maximo:
                return int(respuesta)
            self._salida(f"Escribe un número entre {minimo} y {maximo}.")

    def _pedir_descarte(self, obs: Observation, legal_actions: Sequence[Action]) -> Action:
        while True:
            respuesta = self._pedir(
                "¿Qué cartas descartas? Escribe sus números separados por espacios (ej.: 1 3): "
            )
            if respuesta is None:
                continue
            partes = respuesta.replace(",", " ").split()
            if not partes or not all(p.isdigit() for p in partes):
                self._salida("Escribe los números de las cartas, del 1 al 4.")
                continue
            indices = {int(p) for p in partes}
            if not all(1 <= i <= len(obs.cartas) for i in indices):
                self._salida("Escribe los números de las cartas, del 1 al 4.")
                continue
            accion = Descarte(frozenset(obs.cartas[i - 1] for i in indices))
            if accion in legal_actions:
                return accion
            self._salida("Ese descarte no es válido.")

    @staticmethod
    def _opciones(legal_actions: Sequence[Action]) -> list[tuple[str, object]]:
        """Agrupa las acciones legales en opciones de menú."""
        opciones: list[tuple[str, object]] = []
        for accion in legal_actions:
            if isinstance(accion, Descarte):
                if not any(o[1] == _DESCARTE for o in opciones):
                    opciones.append(("Descartar", _DESCARTE))
            elif isinstance(accion, Envido) and accion.tantos != ENVIDO_POR_DEFECTO:
                if not any(o[1] == _ENVIDO_N for o in opciones):
                    opciones.append((f"Envido N ({ENVIDO_MIN}-{ENVIDO_MAX})", _ENVIDO_N))
            elif isinstance(accion, Envido):
                opciones.append((f"Envido ({ENVIDO_POR_DEFECTO} tantos)", accion))
            elif isinstance(accion, Reenvido):
                if not any(o[1] == _REENVIDO_N for o in opciones):
                    maximo = _maximo_reenvido(legal_actions)
                    opciones.append((f"Reenvido N ({REENVIDO_MIN}-{maximo})", _REENVIDO_N))
            else:
                opciones.append((str(accion), accion))
        return opciones

"""Reglas del mus: qué acciones son legales y cómo cambia el estado al aplicarlas.

La interfaz pública son tres funciones puras:

- :func:`nueva_partida` crea el estado inicial (ya repartido).
- :func:`legal_actions` devuelve la lista de acciones legales para el jugador en turno.
- :func:`apply` devuelve un **nuevo** estado tras aplicar una acción; si la acción es ilegal lanza
  :class:`~musarena.actions.IllegalActionError` y el estado recibido queda intacto.

El motor no sabe quién juega: no hay aquí ni humanos ni bots, solo estados y acciones.
Las reglas implementadas están en ``docs/reglas.md``.
"""

from __future__ import annotations

import random
from itertools import combinations

from musarena.actions import (
    APUESTA_MAX,
    ENVIDO_MAX,
    ENVIDO_POR_DEFECTO,
    REENVIDO_MAX,
    REENVIDO_MIN,
    Action,
    Descarte,
    Envido,
    IllegalActionError,
    Mus,
    NoHayMus,
    NoQuiero,
    Ordago,
    Paso,
    Quiero,
    Reenvido,
)
from musarena.cards import Baraja, ordenar_cartas
from musarena.hands import (
    Lance,
    bonus_juego,
    ganador,
    orden_desde_mano,
    tiene_juego,
    tiene_pares,
    tipo_pares,
)
from musarena.state import (
    LANCES,
    TANTOS_VACA,
    Apuesta,
    Cobro,
    Evento,
    Fase,
    ResultadoLance,
    ResumenMano,
    State,
    TipoResultado,
    nombre_jugador,
    nombre_pareja,
    pareja,
)

__all__ = ["nueva_partida", "legal_actions", "apply", "vacas_para_ganar", "IllegalActionError"]


def vacas_para_ganar(mejor_de: int) -> int:
    """Vacas necesarias para ganar una partida al mejor de 3 (2 vacas) o de 5 (3 vacas)."""
    if mejor_de not in (3, 5):
        raise ValueError("La partida se juega al mejor de 3 o de 5 vacas")
    return mejor_de // 2 + 1


def nueva_partida(
    mejor_de: int = 3,
    seed: int | None = None,
    rng: random.Random | None = None,
    mano: int = 0,
) -> State:
    """Crea una partida nueva con la primera mano ya repartida.

    Se puede pasar una semilla (``seed``) o un generador (``rng``) para que sea reproducible.
    """
    generador = rng if rng is not None else random.Random(seed)
    estado = State(
        vacas_para_ganar=vacas_para_ganar(mejor_de),
        rng=generador,
        baraja=Baraja(generador),
        mano=mano,
    )
    _repartir(estado)
    return estado


# --- Acciones legales -------------------------------------------------------------------------


def legal_actions(state: State) -> list[Action]:
    """Acciones legales del jugador en turno (``state.turno``). Lista vacía si la partida acabó."""
    if state.fase is Fase.FIN:
        return []
    if state.fase is Fase.MUS:
        return [Mus(), NoHayMus()]
    if state.fase is Fase.DESCARTE:
        cartas = state.cartas[state.turno]
        return [
            Descarte(frozenset(grupo))
            for n in range(1, len(cartas) + 1)
            for grupo in combinations(cartas, n)
        ]
    apuesta = state.apuesta
    if apuesta.pareja_apostadora is None:
        envites = [Envido(n) for n in range(ENVIDO_POR_DEFECTO, ENVIDO_MAX + 1)]
        return [Paso(), *envites, Ordago()]
    respuestas: list[Action] = [Quiero(), NoQuiero()]
    if not apuesta.ordago:
        # El total apostado no puede pasar de 40 tantos.
        maximo = min(REENVIDO_MAX, APUESTA_MAX - apuesta.tantos)
        respuestas += [Reenvido(n) for n in range(REENVIDO_MIN, maximo + 1)]
        respuestas.append(Ordago())
    return respuestas


# --- Aplicar una acción -----------------------------------------------------------------------


def apply(state: State, action: Action) -> State:
    """Devuelve el estado resultante de que el jugador en turno haga ``action``.

    La legalidad se comprueba **antes** de copiar y modificar nada, así que una acción ilegal
    nunca deja un estado a medias.
    """
    if action not in legal_actions(state):
        raise IllegalActionError(
            f"Acción ilegal {action!r} (fase: {state.fase.value}, turno: {state.turno})"
        )
    nuevo = state.copiar()
    asiento = nuevo.turno
    if nuevo.fase is Fase.MUS:
        _aplicar_mus(nuevo, asiento, action)
    elif nuevo.fase is Fase.DESCARTE:
        _aplicar_descarte(nuevo, asiento, action)
    else:
        _aplicar_apuesta(nuevo, asiento, action)
    return nuevo


# --- Reparto y fase de mus --------------------------------------------------------------------


def _repartir(s: State) -> None:
    """Baraja las 40 cartas, reparte 4 a cada jugador y abre la fase de mus."""
    s.baraja = Baraja(s.rng)
    s.cartas = [[], [], [], []]
    for asiento in orden_desde_mano(s.mano):
        s.cartas[asiento] = ordenar_cartas(s.baraja.robar(4))
    s.fase = Fase.MUS
    s.turno = s.mano
    s.mus_pedidos = 0
    s.descartes_hechos = 0
    s.lances_pendientes = list(LANCES)
    s.lance = None
    s.apuesta = None
    s.resultados = []
    s.cobros = []
    s.declaraciones = {}
    s.historial = [Evento(None, f"Mano {s.numero_mano}: es mano el {nombre_jugador(s.mano)}")]


def _siguiente(asiento: int) -> int:
    return (asiento + 1) % 4


def _aplicar_mus(s: State, asiento: int, action: Action) -> None:
    s.historial.append(Evento(asiento, str(action), action))
    if isinstance(action, NoHayMus):
        _empezar_lances(s)
        return
    s.mus_pedidos += 1
    if s.mus_pedidos == 4:
        s.historial.append(Evento(None, "Todos piden mus: descartes"))
        s.fase = Fase.DESCARTE
        s.descartes_hechos = 0
        s.turno = s.mano
    else:
        s.turno = _siguiente(asiento)


def _aplicar_descarte(s: State, asiento: int, action: Descarte) -> None:
    descartadas = [c for c in s.cartas[asiento] if c in action.cartas]
    se_queda = [c for c in s.cartas[asiento] if c not in action.cartas]
    # Las cartas tiradas van a la pila antes de robar: si el mazo se acaba a mitad del robo, se
    # barajan todos los descartes, incluidos los que acaba de tirar este jugador.
    s.baraja.descartar(descartadas)
    s.cartas[asiento] = ordenar_cartas(se_queda + s.baraja.robar(len(descartadas)))
    n = len(descartadas)
    s.historial.append(Evento(asiento, f"Se descarta de {n} carta{'s' if n > 1 else ''}"))
    s.descartes_hechos += 1
    if s.descartes_hechos == 4:
        s.fase = Fase.MUS
        s.mus_pedidos = 0
        s.turno = s.mano
    else:
        s.turno = _siguiente(asiento)


# --- Lances -----------------------------------------------------------------------------------


def _empezar_lances(s: State) -> None:
    s.fase = Fase.LANCE
    _siguiente_lance(s)


def _declarar(s: State, lance: Lance) -> list[int]:
    """Declaración pública y obligatoria de pares o de juego. Devuelve quién tiene la jugada."""
    evaluar = tiene_pares if lance is Lance.PARES else tiene_juego
    declaracion = {a: evaluar(s.cartas[a]) for a in orden_desde_mano(s.mano)}
    s.declaraciones[lance] = declaracion
    for a, tiene in declaracion.items():
        texto = f"{lance}: {'sí' if tiene else 'no'}"
        s.historial.append(Evento(a, texto, lance=lance))
    return [a for a, tiene in declaracion.items() if tiene]


def _siguiente_lance(s: State) -> None:
    """Abre el siguiente lance con apuestas, o pasa al recuento si no quedan."""
    while s.lances_pendientes:
        lance = s.lances_pendientes.pop(0)
        orden = orden_desde_mano(s.mano)
        if lance in (Lance.GRANDE, Lance.CHICA):
            participantes = orden
        else:
            participantes = _declarar(s, lance)
            if lance is Lance.JUEGO and not participantes:
                lance = Lance.PUNTO
                participantes = orden
                s.historial.append(Evento(None, "Nadie tiene juego: se juega al punto"))

        if {pareja(a) for a in participantes} == {0, 1}:
            s.lance = lance
            s.apuesta = Apuesta(participantes=tuple(participantes), por_hablar=list(participantes))
            s.turno = participantes[0]
            s.historial.append(Evento(None, f"Se juega a {lance}", lance=lance))
            return

        s.resultados.append(
            ResultadoLance(lance, TipoResultado.SIN_APUESTA, participantes=tuple(participantes))
        )
        texto = "nadie los tiene" if not participantes else "solo una pareja tiene jugada"
        s.historial.append(Evento(None, f"{lance}: no hay apuestas, {texto}", lance=lance))

    _terminar_mano(s, _recuento(s))


def _aplicar_apuesta(s: State, asiento: int, action: Action) -> None:
    ap = s.apuesta
    lance = s.lance
    ap.por_hablar.pop(0)
    s.historial.append(Evento(asiento, str(action), action, lance))

    if isinstance(action, Paso):
        if not ap.por_hablar:
            _cerrar_lance(s, ResultadoLance(lance, TipoResultado.EN_PASO, ap.participantes))
            return
    elif isinstance(action, (Envido, Reenvido, Ordago)):
        # El deje de una primera apuesta es 1; el de una subida, la apuesta anterior.
        ap.deje = 1 if ap.pareja_apostadora is None else ap.tantos
        if isinstance(action, Envido):
            ap.tantos = action.tantos
        elif isinstance(action, Reenvido):
            ap.tantos += action.tantos
        else:
            ap.ordago = True
        ap.pareja_apostadora = pareja(asiento)
        ap.por_hablar = [a for a in ap.participantes if pareja(a) != pareja(asiento)]
    elif isinstance(action, Quiero):
        if ap.ordago:
            _resolver_ordago(s)
            return
        _cerrar_lance(
            s, ResultadoLance(lance, TipoResultado.QUERIDO, ap.participantes, apuesta=ap.tantos)
        )
        return
    elif isinstance(action, NoQuiero) and not ap.por_hablar:
        # Los dos rivales han dicho "no quiero": la pareja apostadora cobra el deje ya.
        ganadora = ap.pareja_apostadora
        if _cobrar(s, ganadora, ap.deje, lance, "no quiero"):
            _terminar_mano(s, ganadora)
            return
        _cerrar_lance(
            s, ResultadoLance(lance, TipoResultado.NO_QUERIDO, ap.participantes, pareja=ganadora)
        )
        return

    s.turno = ap.por_hablar[0]


def _cerrar_lance(s: State, resultado: ResultadoLance) -> None:
    s.resultados.append(resultado)
    s.apuesta = None
    s.lance = None
    _siguiente_lance(s)


def _resolver_ordago(s: State) -> None:
    """Órdago aceptado: se comparan las cartas del lance y el ganador se lleva la vaca."""
    lance = s.lance
    manos = {a: s.cartas[a] for a in s.apuesta.participantes}
    ganadora = pareja(ganador(lance, manos, s.mano))
    s.cobros.append(Cobro(ganadora, 0, lance, "órdago aceptado: gana la vaca"))
    s.historial.append(
        Evento(None, f"Órdago a {lance}: gana la pareja {nombre_pareja(ganadora)}", lance=lance)
    )
    _terminar_mano(s, ganadora)


def _cobrar(s: State, p: int, tantos: int, lance: Lance | None, motivo: str) -> bool:
    """Suma tantos a una pareja. Devuelve ``True`` si con ellos gana la vaca."""
    s.tantos[p] += tantos
    s.cobros.append(Cobro(p, tantos, lance, motivo))
    s.historial.append(
        Evento(None, f"Pareja {nombre_pareja(p)} cobra {tantos} ({lance}: {motivo})", lance=lance)
    )
    return s.tantos[p] >= TANTOS_VACA


# --- Recuento y fin de mano -------------------------------------------------------------------


def _valorar(s: State, r: ResultadoLance) -> tuple[int, int, str] | None:
    """(pareja, tantos, motivo) que corresponden a un lance en el recuento, o ``None``."""
    if not r.participantes:
        return None
    lance = r.lance
    manos = {a: s.cartas[a] for a in r.participantes}
    if r.tipo is TipoResultado.NO_QUERIDO:
        if lance in (Lance.GRANDE, Lance.CHICA):
            return None  # ya se cobró el deje en el momento
        ganadora = r.pareja
    else:
        ganadora = pareja(ganador(lance, manos, s.mano))

    apuesta = r.apuesta if r.tipo is TipoResultado.QUERIDO else 0
    partes = [f"envite {apuesta}"] if apuesta else []
    if lance in (Lance.GRANDE, Lance.CHICA):
        extra = 1 if r.tipo is TipoResultado.EN_PASO else 0
        if extra:
            partes.append("en paso 1")
    elif lance is Lance.PUNTO:
        extra = 1
        partes.append("punto 1")
    else:
        suyos = [a for a in r.participantes if pareja(a) == ganadora]
        if lance is Lance.PARES:
            tipos = [tipo_pares(s.cartas[a]) for a in suyos]
            valores = [int(t) for t in tipos]
            partes += [f"{t} {int(t)}" for t in tipos]
        else:
            valores = [bonus_juego(s.cartas[a]) for a in suyos]
            partes += [f"juego {v}" for v in valores]
        extra = sum(valores)
    tantos = apuesta + extra
    if tantos == 0:
        return None
    return ganadora, tantos, " + ".join(partes)


def _recuento(s: State) -> int | None:
    """Cuenta los lances en orden. Devuelve la pareja que gana la vaca, si alguna llega a 40."""
    for resultado in s.resultados:
        valor = _valorar(s, resultado)
        if valor is None:
            continue
        p, tantos, motivo = valor
        if _cobrar(s, p, tantos, resultado.lance, motivo):
            return p
    return None


def _terminar_mano(s: State, ganador_vaca: int | None) -> None:
    """Enseña las cartas, apunta la vaca si alguien la ha ganado y reparte la siguiente mano."""
    s.manos_jugadas.append(
        ResumenMano(
            numero=s.numero_mano,
            mano=s.mano,
            cartas=tuple(tuple(c) for c in s.cartas),
            cobros=tuple(s.cobros),
            tantos=(s.tantos[0], s.tantos[1]),
            ganador_vaca=ganador_vaca,
            historial=tuple(s.historial),
        )
    )
    s.apuesta = None
    s.lance = None
    if ganador_vaca is not None:
        s.vacas[ganador_vaca] += 1
        s.tantos = [0, 0]
        if s.vacas[ganador_vaca] >= s.vacas_para_ganar:
            s.ganador = ganador_vaca
            s.fase = Fase.FIN
            s.turno = None
            return
    s.mano = _siguiente(s.mano)
    s.numero_mano += 1
    _repartir(s)

"""Lo que ve cada jugador en el navegador, convertido a JSON.

Todo sale de su :class:`~musarena.observation.Observation` (y de la lista de acciones legales
cuando le toca), igual que lo que recibe un bot. Así es **imposible** que el navegador de un
jugador reciba las cartas de otro: ni siquiera están en los datos que se usan para construir
la respuesta.
"""

from __future__ import annotations

from collections.abc import Sequence

from musarena.actions import Action, Descarte, Envido, Reenvido
from musarena.cards import Carta
from musarena.observation import Observation
from musarena.state import Cobro, ResumenMano, nombre_jugador


def carta(c: Carta) -> dict:
    return {"id": f"{c.numero}-{c.palo.value}", "numero": c.numero, "palo": c.palo.value,
            "nombre": str(c)}


def accion(i: int, a: Action) -> dict:
    """Una acción legal con su número en la lista (el navegador manda ese número de vuelta)."""
    datos = {"id": i, "tipo": type(a).__name__, "texto": str(a)}
    if isinstance(a, (Envido, Reenvido)):
        datos["tantos"] = a.tantos
    if isinstance(a, Descarte):
        datos["cartas"] = sorted(f"{c.numero}-{c.palo.value}" for c in a.cartas)
    return datos


def _cobro(c: Cobro) -> dict:
    return {"pareja": c.pareja, "tantos": c.tantos, "lance": c.lance.value if c.lance else None,
            "motivo": c.motivo}


def resumen(r: ResumenMano) -> dict:
    """Una mano terminada: aquí sí van las cartas de los cuatro, porque ya se han enseñado."""
    return {
        "numero": r.numero,
        "mano": r.mano,
        "cartas": [[carta(c) for c in cartas] for cartas in r.cartas],
        "cobros": [_cobro(c) for c in r.cobros],
        "tantos": list(r.tantos),
        "ganador_vaca": r.ganador_vaca,
    }


def vista(obs: Observation, legales: Sequence[Action], jugadores: Sequence[dict],
          version: int) -> dict:
    """Todo lo que necesita la página de la mesa para un asiento."""
    ap = obs.apuesta
    return {
        "version": version,
        "asiento": obs.asiento,
        "pareja": obs.pareja,
        "jugadores": list(jugadores),
        "cartas": [carta(c) for c in obs.cartas],
        "fase": obs.fase.value,
        "turno": obs.turno,
        "es_mi_turno": obs.es_mi_turno,
        "mano": obs.mano,
        "corrida": obs.corrida,
        "numero_mano": obs.numero_mano,
        "lance": obs.lance.value if obs.lance else None,
        "apuesta": None if ap is None else {
            "tantos": ap.tantos, "deje": ap.deje, "ordago": ap.ordago,
            "pareja_apostadora": ap.pareja_apostadora, "por_hablar": list(ap.por_hablar),
        },
        "tantos": list(obs.tantos),
        "vacas": list(obs.vacas),
        "vacas_para_ganar": obs.vacas_para_ganar,
        "declaraciones": [{"lance": lance.value, "tiene": list(valores)}
                          for lance, valores in obs.declaraciones],
        "historial": [{"asiento": e.asiento,
                       "quien": None if e.asiento is None else nombre_jugador(e.asiento),
                       "texto": e.texto} for e in obs.historial],
        "chat": [{"asiento": m.asiento, "quien": nombre_jugador(m.asiento), "texto": m.texto}
                 for m in obs.chat],
        "manos_jugadas": [resumen(r) for r in obs.manos_jugadas[-5:]],
        "ganador": obs.ganador,
        "acciones": [accion(i, a) for i, a in enumerate(legales)] if obs.es_mi_turno else [],
    }

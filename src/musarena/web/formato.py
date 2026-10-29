"""Formatos de los torneos privados: fase de grupos, cuadro (eliminatoria) y liga.

Aquí solo hay lógica pura (ni base de datos ni web), para poder probarla a fondo:

- :class:`Formato`: lo que elige el organizador antes de abrir el torneo.
- :meth:`Formato.resolver`: el formato concreto según las parejas que se han inscrito. En modo
  ``"auto"`` sigue la regla del equipo: **más de 16 parejas, fase de grupos**; con 16 o menos,
  cuadro directo (octavos si son 16, cuartos si son 8, semifinales si son 4).
- :func:`repartir_grupos`, :func:`enfrentamientos_liga`, :func:`clasificar`: grupos y ligas.
- :func:`primera_ronda`: el cuadro con cabezas de serie y **pases directos** cuando el número de
  parejas no es potencia de 2 (con 12 parejas, el cuadro es de 16 y los 4 mejores cabezas de
  serie pasan solos a la segunda ronda).
"""

from __future__ import annotations

import math
import random
from collections.abc import Hashable, Sequence
from dataclasses import asdict, dataclass, replace

#: Tipos de formato que se pueden elegir.
TIPOS_FORMATO = ("auto", "eliminatoria", "grupos", "liga")
MIN_PAREJAS, MAX_PAREJAS = 2, 64
#: Por encima de este número de parejas, el modo automático hace fase de grupos.
LIMITE_SIN_GRUPOS = 16

_RONDAS = {2: "Final", 4: "Semifinales", 8: "Cuartos de final", 16: "Octavos de final",
           32: "Dieciseisavos de final", 64: "Treintaidosavos de final"}


@dataclass(frozen=True)
class Formato:
    """Formato de un torneo privado.

    - ``tipo``: ``"auto"`` (grupos solo si hay más de 16 parejas), ``"eliminatoria"`` (cuadro
      directo), ``"grupos"`` (grupos y luego cuadro) o ``"liga"`` (todos contra todos).
    - ``max_parejas``: plazas del torneo.
    - ``tam_grupo`` y ``pasan_por_grupo``: parejas por grupo y cuántas pasan al cuadro.
    - ``mejor_de`` y ``mejor_de_final``: vacas de cada partido y de la final.
    - ``tercer_puesto``: si se juega el partido por el tercer puesto.
    """

    tipo: str = "auto"
    max_parejas: int = 16
    tam_grupo: int = 4
    pasan_por_grupo: int = 2
    mejor_de: int = 3
    mejor_de_final: int = 3
    tercer_puesto: bool = False

    def validar(self) -> None:
        """Lanza ``ValueError`` (con un mensaje para el usuario) si algo no tiene sentido."""
        if self.tipo not in TIPOS_FORMATO:
            raise ValueError(f"Formato desconocido: {self.tipo!r}")
        if not MIN_PAREJAS <= self.max_parejas <= MAX_PAREJAS:
            raise ValueError(f"El torneo tiene que ser de {MIN_PAREJAS} a {MAX_PAREJAS} parejas")
        if not 3 <= self.tam_grupo <= 8:
            raise ValueError("Los grupos tienen que ser de 3 a 8 parejas")
        if not 1 <= self.pasan_por_grupo < self.tam_grupo:
            raise ValueError("De cada grupo tiene que pasar al menos 1 pareja y no todas")
        if self.mejor_de not in (3, 5) or self.mejor_de_final not in (3, 5):
            raise ValueError("Los partidos son al mejor de 3 o de 5 vacas")

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> Formato:
        campos = {k: datos[k] for k in cls.__dataclass_fields__ if k in datos}
        return cls(**campos)

    def resolver(self, n: int) -> Formato:
        """El formato concreto para ``n`` parejas inscritas (nunca devuelve ``"auto"``).

        Si con los grupos elegidos no pasaría nadie a jugar (por ejemplo, grupos de 3 en los
        que pasan 3), se ajusta lo justo para que el torneo se pueda jugar.
        """
        tipo = self.tipo
        if tipo == "auto":
            tipo = "grupos" if n > LIMITE_SIN_GRUPOS else "eliminatoria"
            ajustado = replace(self, tipo=tipo, tam_grupo=4, pasan_por_grupo=2)
        else:
            ajustado = replace(self, tipo=tipo)
        if tipo == "grupos":
            n_grupos = max(1, math.ceil(n / ajustado.tam_grupo))
            menor = n // n_grupos  # el grupo más pequeño
            pasan = max(1, min(ajustado.pasan_por_grupo, menor - 1))
            if n_grupos * pasan < 2:  # un solo grupo del que pasaría una pareja: es una liga
                return replace(ajustado, tipo="liga")
            ajustado = replace(ajustado, pasan_por_grupo=pasan)
        return ajustado


# --- Cuadro ---------------------------------------------------------------------------


def nombre_ronda(parejas_en_ronda: int) -> str:
    """"Final", "Semifinales", "Cuartos de final"… según cuántas parejas juegan la ronda."""
    return _RONDAS.get(parejas_en_ronda, f"Ronda de {parejas_en_ronda}")


def tamano_cuadro(clasificados: int) -> int:
    """Potencia de 2 más pequeña en la que caben ``clasificados`` parejas (mínimo 2)."""
    return max(2, 1 << (clasificados - 1).bit_length())


def orden_cabezas(tamano: int) -> list[int]:
    """Cabezas de serie (1 = la mejor) en el orden en que se colocan en el cuadro.

    Es el orden clásico del tenis: el 1 y el 2 solo se pueden cruzar en la final, el 1 juega
    contra el último, etc. Para 8: ``[1, 8, 4, 5, 2, 7, 3, 6]``.
    """
    orden = [1]
    while len(orden) < tamano:
        suma = 2 * len(orden) + 1
        orden = [x for semilla in orden for x in (semilla, suma - semilla)]
    return orden


def primera_ronda(cabezas: Sequence[Hashable]) -> list[tuple[Hashable | None, Hashable | None]]:
    """Partidos de la primera ronda del cuadro.

    ``cabezas`` va de mejor a peor. Los huecos que sobran hasta la potencia de 2 son **pases
    directos** (``None``) y les tocan a las mejores cabezas de serie.
    """
    if len(cabezas) < 2:
        raise ValueError("Hacen falta al menos 2 parejas para un cuadro")
    tamano = tamano_cuadro(len(cabezas))
    huecos = [cabezas[s - 1] if s <= len(cabezas) else None for s in orden_cabezas(tamano)]
    return [(huecos[i], huecos[i + 1]) for i in range(0, tamano, 2)]


def rondas_del_cuadro(clasificados: int) -> list[str]:
    """Nombres de las rondas que se jugarán, de la primera a la final."""
    tamano = tamano_cuadro(clasificados)
    nombres = []
    while tamano >= 2:
        nombres.append(nombre_ronda(tamano))
        tamano //= 2
    return nombres


# --- Grupos y liga --------------------------------------------------------------------


def repartir_grupos(parejas: Sequence[Hashable], tam_grupo: int,
                    rng: random.Random) -> list[list[Hashable]]:
    """Sorteo de grupos: lo más iguales posible (se diferencian como mucho en una pareja)."""
    orden = list(parejas)
    rng.shuffle(orden)
    n_grupos = max(1, math.ceil(len(orden) / tam_grupo))
    grupos: list[list[Hashable]] = [[] for _ in range(n_grupos)]
    for i, pareja in enumerate(orden):
        grupos[i % n_grupos].append(pareja)
    return grupos


def enfrentamientos_liga(parejas: Sequence[Hashable]) -> list[list[tuple[Hashable, Hashable]]]:
    """Calendario de todos contra todos, por jornadas (método del círculo).

    Con un número impar de parejas, en cada jornada una descansa.
    """
    lista: list[Hashable | None] = list(parejas)
    if len(lista) % 2:
        lista.append(None)
    n = len(lista)
    jornadas = []
    for _ in range(n - 1):
        jornada = [(lista[i], lista[n - 1 - i]) for i in range(n // 2)]
        jornadas.append([(a, b) for a, b in jornada if a is not None and b is not None])
        lista = [lista[0], lista[-1], *lista[1:-1]]  # el primero fijo, los demás giran
    return jornadas


@dataclass(frozen=True)
class Resultado:
    """Resultado de un partido terminado entre las parejas ``a`` y ``b``."""

    a: Hashable
    b: Hashable
    ganador: Hashable
    vacas_a: int = 0
    vacas_b: int = 0
    tantos_a: int = 0
    tantos_b: int = 0


@dataclass
class Fila:
    """Una pareja en la tabla de un grupo o de la liga."""

    pareja: Hashable
    jugados: int = 0
    ganados: int = 0
    perdidos: int = 0
    vacas_favor: int = 0
    vacas_contra: int = 0
    tantos_favor: int = 0
    tantos_contra: int = 0

    @property
    def puntos(self) -> int:
        """Un punto por partido ganado."""
        return self.ganados

    def clave(self) -> tuple:
        """Orden de la tabla: puntos, diferencia de vacas y diferencia de tantos."""
        return (-self.puntos, -(self.vacas_favor - self.vacas_contra),
                -(self.tantos_favor - self.tantos_contra), -self.vacas_favor)


def clasificar(parejas: Sequence[Hashable], resultados: Sequence[Resultado]) -> list[Fila]:
    """Tabla de un grupo o de una liga, de primera a última.

    Desempates, por orden: partidos ganados, diferencia de vacas, diferencia de tantos, vacas
    a favor y, si aún empatan, el partido entre ellas (si lo jugaron).
    """
    filas = {p: Fila(p) for p in parejas}
    ganador_entre: dict[frozenset, Hashable] = {}
    for r in resultados:
        if r.a not in filas or r.b not in filas:
            continue
        for propia, ajena, vf, vc, tf, tc in ((r.a, r.b, r.vacas_a, r.vacas_b, r.tantos_a,
                                               r.tantos_b),
                                              (r.b, r.a, r.vacas_b, r.vacas_a, r.tantos_b,
                                               r.tantos_a)):
            f = filas[propia]
            f.jugados += 1
            f.ganados += r.ganador == propia
            f.perdidos += r.ganador == ajena
            f.vacas_favor += vf
            f.vacas_contra += vc
            f.tantos_favor += tf
            f.tantos_contra += tc
        ganador_entre[frozenset((r.a, r.b))] = r.ganador
    orden = sorted(filas.values(), key=Fila.clave)
    # Empate exacto entre dos seguidas: manda el partido entre ellas.
    for i in range(len(orden) - 1):
        x, y = orden[i], orden[i + 1]
        entre = ganador_entre.get(frozenset((x.pareja, y.pareja)))
        if x.clave() == y.clave() and entre == y.pareja:
            orden[i], orden[i + 1] = y, x
    return orden


def cabezas_tras_grupos(tablas: Sequence[Sequence[Fila]], pasan: int) -> list[tuple[Hashable, int]]:
    """Clasificados de los grupos ordenados como cabezas de serie, con el grupo de cada uno.

    Primero todos los primeros (el mejor primero delante), luego los segundos, etc. Así los
    primeros de grupo se cruzan con segundos de otros grupos y no se encuentran hasta el final.
    """
    cabezas = []
    for puesto in range(pasan):
        del_puesto = [(tabla[puesto], g) for g, tabla in enumerate(tablas) if puesto < len(tabla)]
        del_puesto.sort(key=lambda x: x[0].clave())
        cabezas += [(fila.pareja, g) for fila, g in del_puesto]
    return cabezas


def separar_grupos(partidos: list[tuple[Hashable | None, Hashable | None]],
                   grupo_de: dict[Hashable, int]) -> list[tuple[Hashable | None, Hashable | None]]:
    """Evita, si se puede, que en la primera ronda se crucen dos parejas del mismo grupo.

    Intercambia la segunda pareja de un partido problemático con la segunda de otro partido
    siempre que los dos queden bien. Las cabezas de serie (primeras de cada partido) no se mueven.
    """
    partidos = list(partidos)

    def choca(a, b) -> bool:
        return a is not None and b is not None and grupo_de.get(a) == grupo_de.get(b)

    for i, (a, b) in enumerate(partidos):
        if not choca(a, b):
            continue
        for j, (c, d) in enumerate(partidos):
            if j != i and d is not None and not choca(a, d) and not choca(c, b):
                partidos[i], partidos[j] = (a, d), (c, b)
                break
    return partidos


# --- Descripción para el usuario ------------------------------------------------------


def describir(formato: Formato, n: int) -> str:
    """Cómo sería el torneo con ``n`` parejas, en una frase."""
    f = formato.resolver(n)
    final = f" La final, al mejor de {f.mejor_de_final}." if f.mejor_de_final != f.mejor_de else ""
    vacas = f"Partidos al mejor de {f.mejor_de} vacas.{final}"
    if f.tipo == "liga":
        return (f"{n} parejas: liga todos contra todos ({n * (n - 1) // 2} partidos). "
                f"Gana la primera de la tabla. {vacas}")
    if f.tipo == "grupos":
        n_grupos = max(1, math.ceil(n / f.tam_grupo))
        tamanos = sorted({len(g) for g in repartir_grupos(range(n), f.tam_grupo, random.Random(0))})
        de = " o ".join(str(t) for t in tamanos)
        q = n_grupos * f.pasan_por_grupo
        texto = (f"{n} parejas: {n_grupos} grupo{'s' if n_grupos > 1 else ''} de {de}, pasan "
                 f"{f.pasan_por_grupo} de cada uno ({q}). ")
    else:
        q = n
        texto = f"{n} parejas: cuadro directo. "
    tamano = tamano_cuadro(q)
    pases = tamano - q
    rondas = rondas_del_cuadro(q)
    texto += f"Cuadro de {tamano}"
    if pases:
        s = "s" if pases > 1 else ""
        texto += f" ({pases} pase{s} directo{s} a la segunda ronda)"
    texto += ": " + ", ".join(r.lower() if i else r for i, r in enumerate(rondas)) + ". "
    if f.tercer_puesto and tamano >= 4:
        texto += "Con partido por el tercer puesto. "
    return texto + vacas

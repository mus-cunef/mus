"""Torneos privados entre personas: inscripción por parejas, sorteo, cuadro y estadísticas.

Cómo funciona un torneo:

1. **Crear.** Un usuario con sesión elige el nombre, el formato (:class:`~.formato.Formato`) y la
   fecha límite de inscripción. Recibe un **código de invitación**: el enlace
   ``/#/t/<código>`` es lo que pasa a sus amigos. Sin el código, el torneo no se ve.
2. **Inscribirse.** Cada pareja la inscribe uno de sus jugadores con el nombre de usuario de su
   compañero; la pareja cuenta cuando el compañero **acepta**. Nadie puede estar en dos parejas
   del mismo torneo.
3. **Sorteo.** Al llegar la fecha límite (o antes, si el organizador lo decide) se sortea con las
   parejas confirmadas: grupos, liga o cuadro, según el formato.
4. **Jugar.** Cada partido tiene su mesa: la pareja A en los asientos 0 y 2 y la B en el 1 y el 3.
   Cada jugador entra con su sesión (no hay enlaces que se puedan pasar a otro). La mesa guarda
   cada jugada en la base de datos; al terminar, el resultado se apunta solo (nadie lo puede
   falsear) y el ganador avanza. El organizador puede dar un partido por ganado si una pareja no
   se presenta.
"""

from __future__ import annotations

import random
import secrets
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, delete, func, insert, or_, select, update

from musarena.web.bd import parejas, partidos, torneos, usuarios
from musarena.web.config import Config
from musarena.web.cuentas import Cuentas, Usuario
from musarena.web.formato import (
    Formato,
    Resultado,
    cabezas_tras_grupos,
    clasificar,
    describir,
    enfrentamientos_liga,
    nombre_ronda,
    primera_ronda,
    repartir_grupos,
    separar_grupos,
)
from musarena.web.mesas import HUMANO, ErrorMesa, GestorMesas, Mesa

#: Torneos sin terminar que puede organizar a la vez una misma persona.
MAX_ACTIVOS = 10
#: Como mucho, la fecha límite puede estar a un año vista.
MAX_PLAZO = 365 * 24 * 3600
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _texto(valor: object, maximo: int, que: str) -> str:
    """Texto de una línea sin caracteres de control ni espacios de más."""
    limpio = (" ".join("".join(ch for ch in valor if ch.isprintable()).split())
              if isinstance(valor, str) else "")
    if not limpio or len(limpio) > maximo:
        raise ErrorMesa(f"{que}: de 1 a {maximo} caracteres")
    return limpio


def estadisticas_partida(mesa: Mesa) -> dict:
    """Números de un partido terminado, por pareja del motor (0 = asientos 0 y 2)."""
    s = mesa.match.state
    datos = {p: {"tantos": 0, "manos": 0, "ordagos": 0, "ordagos_ganados": 0, "envites": 0}
             for p in (0, 1)}
    for mano in s.manos_jugadas:
        cobrado = [0, 0]
        for cobro in mano.cobros:
            cobrado[cobro.pareja] += cobro.tantos
            if cobro.motivo.startswith("órdago aceptado"):
                datos[cobro.pareja]["ordagos_ganados"] += 1
        for p in (0, 1):
            datos[p]["tantos"] += cobrado[p]
        if cobrado[0] != cobrado[1]:
            datos[0 if cobrado[0] > cobrado[1] else 1]["manos"] += 1
    for asiento, accion in mesa.acciones:
        if accion["tipo"] == "Ordago":
            datos[asiento % 2]["ordagos"] += 1
        elif accion["tipo"] in ("Envido", "Reenvido"):
            datos[asiento % 2]["envites"] += 1
    for p in (0, 1):
        datos[p]["vacas"] = s.vacas[p]
    return {"a": datos[0], "b": datos[1], "manos_jugadas": len(s.manos_jugadas)}


class Privados:
    """Los torneos privados, guardados en la base de datos."""

    def __init__(self, motor: Engine, cuentas: Cuentas, mesas: GestorMesas, config: Config,
                 reloj: Callable[[], float] = time.time) -> None:
        self.motor = motor
        self.cuentas = cuentas
        self.mesas = mesas
        self.config = config
        self.reloj = reloj
        # Un cambio de estado de un torneo cada vez (sorteos, resultados, avances del cuadro).
        self._lock = threading.RLock()
        mesas.restaurador = self._restaurar_mesa

    # --- Crear y listar -------------------------------------------------------------------

    def crear(self, usuario: Usuario, nombre: object, formato: object,
              fecha_limite: object) -> str:
        """Crea un torneo y devuelve su código de invitación."""
        nombre = _texto(nombre, 60, "El nombre del torneo")
        if not isinstance(formato, dict):
            raise ErrorMesa("Falta el formato")
        try:
            f = Formato.desde_dict(formato)
            f.validar()
        except (TypeError, ValueError) as e:
            raise ErrorMesa(str(e) or "Formato no válido") from None
        ahora = self.reloj()
        if (not isinstance(fecha_limite, (int, float))
                or not ahora < fecha_limite < ahora + MAX_PLAZO):
            raise ErrorMesa("La fecha límite tiene que ser futura (y como mucho dentro de un año)")
        codigo = secrets.token_urlsafe(12)
        with self._lock, self.motor.begin() as c:
            activos = c.execute(select(func.count()).select_from(torneos).where(
                torneos.c.organizador == usuario.id,
                torneos.c.estado.in_(("inscripcion", "en_curso")))).scalar_one()
            if activos >= MAX_ACTIVOS:
                raise ErrorMesa(f"Ya organizas {MAX_ACTIVOS} torneos sin terminar", 429)
            c.execute(insert(torneos).values(
                codigo=codigo, nombre=nombre, organizador=usuario.id, formato=f.a_dict(),
                fecha_limite=float(fecha_limite), estado="inscripcion",
                semilla=random.SystemRandom().randrange(2**31), creado=ahora))
        return codigo

    def lista(self, usuario: Usuario) -> list[dict]:
        """Los torneos que organiza el usuario o en los que está inscrito."""
        with self.motor.connect() as c:
            mios = select(parejas.c.torneo).where(
                or_(parejas.c.jugador1 == usuario.id, parejas.c.jugador2 == usuario.id))
            filas = c.execute(select(torneos).where(
                or_(torneos.c.organizador == usuario.id, torneos.c.id.in_(mios)))
                .order_by(torneos.c.creado.desc())).all()
        for fila in filas:
            self._al_dia(fila.codigo)
        with self.motor.connect() as c:
            filas = c.execute(select(torneos).where(torneos.c.id.in_([f.id for f in filas]))
                              .order_by(torneos.c.creado.desc())).all()
            confirmadas = dict(c.execute(
                select(parejas.c.torneo, func.count()).where(parejas.c.confirmada)
                .group_by(parejas.c.torneo)).all())
        return [{"codigo": f.codigo, "nombre": f.nombre, "estado": f.estado,
                 "fecha_limite": f.fecha_limite, "parejas": confirmadas.get(f.id, 0),
                 "max_parejas": f.formato["max_parejas"],
                 "organizo": f.organizador == usuario.id} for f in filas]

    # --- Inscripción ----------------------------------------------------------------------

    def inscribir(self, usuario: Usuario, codigo: str, nombre: object,
                  companero: object) -> int:
        """Inscribe una pareja (queda pendiente hasta que el compañero acepte)."""
        nombre = _texto(nombre, 30, "El nombre de la pareja")
        otro = self.cuentas.buscar(companero) if isinstance(companero, str) else None
        if otro is None:
            raise ErrorMesa("No hay ningún usuario con ese nombre: tu compañero tiene que "
                            "crearse una cuenta primero", 404)
        if otro.id == usuario.id:
            raise ErrorMesa("Tu compañero tiene que ser otra persona")
        with self._lock, self.motor.begin() as c:
            t = self._abierto(c, codigo)
            for quien, texto in ((usuario, "Ya estás en una pareja de este torneo"),
                                 (otro, f"{otro.nombre} ya está en una pareja de este torneo")):
                if self._pareja_de(c, t.id, quien.id) is not None:
                    raise ErrorMesa(texto, 409)
            if c.execute(select(parejas.c.id).where(
                    parejas.c.torneo == t.id,
                    func.lower(parejas.c.nombre) == nombre.lower())).first():
                raise ErrorMesa("Ya hay una pareja con ese nombre", 409)
            if self._confirmadas(c, t.id) >= t.formato["max_parejas"]:
                raise ErrorMesa("El torneo está completo", 409)
            return c.execute(insert(parejas).values(
                torneo=t.id, nombre=nombre, jugador1=usuario.id, jugador2=otro.id,
                confirmada=False, creada=self.reloj())).inserted_primary_key[0]

    def aceptar(self, usuario: Usuario, codigo: str, pareja_id: int) -> None:
        """El compañero invitado acepta: la pareja queda inscrita."""
        with self._lock, self.motor.begin() as c:
            t = self._abierto(c, codigo)
            p = c.execute(select(parejas).where(parejas.c.id == pareja_id,
                                                parejas.c.torneo == t.id)).first()
            if p is None or p.jugador2 != usuario.id:
                raise ErrorMesa("No tienes ninguna invitación de esa pareja", 404)
            if p.confirmada:
                return
            if self._confirmadas(c, t.id) >= t.formato["max_parejas"]:
                raise ErrorMesa("El torneo ya está completo", 409)
            c.execute(update(parejas).where(parejas.c.id == p.id).values(confirmada=True))

    def retirar(self, usuario: Usuario, codigo: str, pareja_id: int) -> None:
        """Borra una pareja (o rechaza la invitación) antes del sorteo."""
        with self._lock, self.motor.begin() as c:
            t = self._torneo(c, codigo)
            if t.estado != "inscripcion":
                raise ErrorMesa("El torneo ya ha empezado: las parejas no se pueden retirar", 409)
            p = c.execute(select(parejas).where(parejas.c.id == pareja_id,
                                                parejas.c.torneo == t.id)).first()
            if p is None:
                raise ErrorMesa("Esa pareja no existe", 404)
            if usuario.id not in (p.jugador1, p.jugador2, t.organizador):
                raise ErrorMesa("No puedes retirar esa pareja", 403)
            c.execute(delete(parejas).where(parejas.c.id == p.id))

    # --- Organizador ----------------------------------------------------------------------

    def empezar(self, usuario: Usuario, codigo: str) -> None:
        """Cierra la inscripción y sortea (antes de la fecha límite, si se quiere)."""
        with self._lock, self.motor.begin() as c:
            t = self._torneo(c, codigo)
            self._solo_organizador(t, usuario)
            if t.estado != "inscripcion":
                raise ErrorMesa("El torneo ya ha empezado", 409)
            if self._confirmadas(c, t.id) < 2:
                raise ErrorMesa("Hacen falta al menos 2 parejas confirmadas", 409)
            self._sortear(c, t)

    def cancelar(self, usuario: Usuario, codigo: str) -> None:
        with self._lock, self.motor.begin() as c:
            t = self._torneo(c, codigo)
            self._solo_organizador(t, usuario)
            if t.estado in ("terminado", "cancelado"):
                raise ErrorMesa("El torneo ya está cerrado", 409)
            for p in c.execute(select(partidos.c.mesa).where(partidos.c.torneo == t.id,
                                                              partidos.c.mesa.is_not(None))):
                self.mesas.quitar(p.mesa)
            c.execute(update(torneos).where(torneos.c.id == t.id).values(estado="cancelado"))

    def dar_ganador(self, usuario: Usuario, codigo: str, partido_id: int, pareja_id: int) -> None:
        """El organizador da un partido por ganado (por ejemplo, si una pareja no se presenta)."""
        with self._lock, self.motor.begin() as c:
            t = self._torneo(c, codigo)
            self._solo_organizador(t, usuario)
            p = self._partido(c, t, partido_id)
            if p.estado not in ("listo", "jugando"):
                raise ErrorMesa("Ese partido no se puede dar por ganado ahora", 409)
            if pareja_id not in (p.pareja_a, p.pareja_b):
                raise ErrorMesa("Esa pareja no juega este partido")
            if p.mesa:
                self.mesas.quitar(p.mesa)
            gana = (p.mejor_de + 1) // 2
            a_gana = pareja_id == p.pareja_a
            c.execute(update(partidos).where(partidos.c.id == p.id).values(
                estado="terminado", ganador=pareja_id, pase=True, mesa=None, tokens=None,
                vacas_a=gana if a_gana else 0, vacas_b=0 if a_gana else gana,
                actualizado=self.reloj()))
            self._avanzar(c, t)

    # --- Jugar ----------------------------------------------------------------------------

    def entrar(self, usuario: Usuario, codigo: str, partido_id: int) -> dict:
        """Mesa y código de asiento de un jugador para su partido (la crea si hace falta)."""
        with self._lock:
            with self.motor.begin() as c:
                t = self._torneo(c, codigo)
                if t.estado != "en_curso":
                    raise ErrorMesa("El torneo no está en juego", 409)
                p = self._partido(c, t, partido_id)
                if p.estado not in ("listo", "jugando"):
                    raise ErrorMesa("Este partido no se puede jugar ahora", 409)
                asientos = self._asientos(c, p)
                if usuario.id not in asientos:
                    raise ErrorMesa("No juegas este partido", 403)
                if p.mesa is None:
                    mesa_id = secrets.token_urlsafe(9)
                    tokens = {a: secrets.token_urlsafe(16) for a in range(4)}
                    c.execute(update(partidos).where(partidos.c.id == p.id).values(
                        estado="jugando", mesa=mesa_id, tokens=tokens, acciones=[],
                        semilla=random.SystemRandom().randrange(2**32),
                        actualizado=self.reloj()))
                    p = self._partido(c, t, partido_id)
            mesa = self.mesas.obtener(p.mesa)
        asiento = asientos.index(usuario.id)
        return {"mesa": mesa.id, "token": mesa.tokens[asiento], "asiento": asiento}

    def _asientos(self, c, p) -> list[int]:
        """Usuario de cada asiento: la pareja A en el 0 y el 2, la B en el 1 y el 3."""
        a = c.execute(select(parejas).where(parejas.c.id == p.pareja_a)).first()
        b = c.execute(select(parejas).where(parejas.c.id == p.pareja_b)).first()
        return [a.jugador1, b.jugador1, a.jugador2, b.jugador2]

    def _restaurar_mesa(self, mesa_id: str) -> Mesa | None:
        """La mesa de un partido en juego, reconstruida desde la base de datos.

        No toma el cerrojo de los torneos: la llama :class:`GestorMesas` con el suyo.
        """
        with self.motor.connect() as c:
            p = c.execute(select(partidos).where(partidos.c.mesa == mesa_id)).first()
            if p is None or p.estado not in ("jugando", "terminado"):
                return None
            asientos = self._asientos(c, p)
            nombres = dict(c.execute(select(usuarios.c.id, usuarios.c.nombre).where(
                usuarios.c.id.in_(asientos))).all())
        mesa = Mesa([HUMANO] * 4, p.mejor_de, self.config, self.mesas.reloj,
                    nombres=[nombres[u] for u in asientos], id=mesa_id, seed=p.semilla,
                    tokens_iniciales={int(k): v for k, v in p.tokens.items()},
                    al_cambiar=self._guardar_jugada(p.id))
        mesa.restaurar(p.acciones or [])
        return mesa

    def _guardar_jugada(self, partido_id: int) -> Callable[[Mesa], None]:
        def guardar(mesa: Mesa) -> None:
            with self._lock, self.motor.begin() as c:
                p = c.execute(select(partidos).where(partidos.c.id == partido_id)).first()
                if p is None or p.mesa != mesa.id or p.estado != "jugando":
                    return  # el organizador lo dio por ganado o se canceló el torneo
                valores: dict[str, Any] = {"acciones": list(mesa.acciones),
                                           "actualizado": self.reloj()}
                if mesa.match.terminada:
                    datos = estadisticas_partida(mesa)
                    valores.update(
                        estado="terminado", estadisticas=datos,
                        ganador=p.pareja_a if mesa.match.ganador == 0 else p.pareja_b,
                        vacas_a=datos["a"]["vacas"], vacas_b=datos["b"]["vacas"],
                        tantos_a=datos["a"]["tantos"], tantos_b=datos["b"]["tantos"])
                c.execute(update(partidos).where(partidos.c.id == p.id).values(**valores))
                if mesa.match.terminada:
                    self._avanzar(c, c.execute(select(torneos).where(
                        torneos.c.id == p.torneo)).first())
        return guardar

    # --- Sorteo y avance ------------------------------------------------------------------

    def _al_dia(self, codigo: str) -> None:
        """Si ha pasado la fecha límite, cierra la inscripción y sortea."""
        with self.motor.connect() as c:
            t = c.execute(select(torneos).where(torneos.c.codigo == codigo)).first()
        if t is None or t.estado != "inscripcion" or self.reloj() < t.fecha_limite:
            return
        with self._lock, self.motor.begin() as c:
            t = self._torneo(c, codigo)
            if t.estado == "inscripcion" and self._confirmadas(c, t.id) >= 2:
                self._sortear(c, t)

    def _sortear(self, c, t) -> None:
        c.execute(delete(parejas).where(parejas.c.torneo == t.id, parejas.c.confirmada.is_(False)))
        ids = sorted(fila.id for fila in c.execute(
            select(parejas.c.id).where(parejas.c.torneo == t.id)))
        f = Formato.desde_dict(t.formato).resolver(len(ids))
        rng = random.Random(t.semilla)
        rng.shuffle(ids)
        nuevos = []
        if f.tipo == "liga":
            for j, jornada in enumerate(enfrentamientos_liga(ids)):
                nuevos += [self._nuevo(t, "liga", a, b, f.mejor_de, jornada=j) for a, b in jornada]
        elif f.tipo == "grupos":
            for g, grupo in enumerate(repartir_grupos(ids, f.tam_grupo, rng)):
                c.execute(update(parejas).where(parejas.c.id.in_(grupo)).values(grupo=g))
                for j, jornada in enumerate(enfrentamientos_liga(grupo)):
                    nuevos += [self._nuevo(t, "grupos", a, b, f.mejor_de, grupo=g, jornada=j)
                               for a, b in jornada]
        if nuevos:
            c.execute(insert(partidos), nuevos)
        c.execute(update(torneos).where(torneos.c.id == t.id).values(
            estado="en_curso", resuelto=f.a_dict()))
        if f.tipo == "eliminatoria":
            self._crear_cuadro(c, t, f, ids, {})
        self._avanzar(c, t)

    def _nuevo(self, t, fase: str, a: int | None, b: int | None, mejor_de: int, **otros) -> dict:
        datos = {"torneo": t.id, "fase": fase, "pareja_a": a, "pareja_b": b,
                 "mejor_de": mejor_de,
                 "estado": "listo" if a is not None and b is not None else "esperando",
                 "pase": False, "vacas_a": 0, "vacas_b": 0, "tantos_a": 0, "tantos_b": 0,
                 "grupo": None, "jornada": None, "ronda": None, "posicion": None,
                 "ganador": None}
        datos.update(otros)
        return datos

    def _crear_cuadro(self, c, t, f: Formato, cabezas: list[int],
                      grupo_de: dict[int, int]) -> None:
        primeros = primera_ronda(cabezas)
        if grupo_de:
            primeros = separar_grupos(primeros, grupo_de)
        tamano = 2 * len(primeros)
        n_rondas = tamano.bit_length() - 1
        nuevos = []
        for ronda in range(n_rondas):
            mejor_de = f.mejor_de_final if ronda == n_rondas - 1 else f.mejor_de
            for pos in range(tamano >> (ronda + 1)):
                a, b = primeros[pos] if ronda == 0 else (None, None)
                datos = self._nuevo(t, "cuadro", a, b, mejor_de, ronda=ronda, posicion=pos)
                if ronda == 0 and (a is None) != (b is None):  # pase directo
                    datos.update(estado="terminado", ganador=a or b, pase=True)
                nuevos.append(datos)
        if f.tercer_puesto and n_rondas >= 2:
            nuevos.append(self._nuevo(t, "tercero", None, None, f.mejor_de, ronda=n_rondas - 1,
                                      posicion=0))
        c.execute(insert(partidos), nuevos)

    def _avanzar(self, c, t) -> None:
        """Mueve a los ganadores por el cuadro, crea el cuadro al acabar los grupos y cierra
        el torneo al jugarse el último partido. Se puede llamar las veces que haga falta."""
        t = c.execute(select(torneos).where(torneos.c.id == t.id)).first()
        f = Formato.desde_dict(t.resuelto)
        todos = c.execute(select(partidos).where(partidos.c.torneo == t.id)).all()
        if f.tipo == "grupos" and not any(p.fase == "cuadro" for p in todos):
            de_grupos = [p for p in todos if p.fase == "grupos"]
            if de_grupos and all(p.estado == "terminado" for p in de_grupos):
                grupo_de = dict(c.execute(select(parejas.c.id, parejas.c.grupo).where(
                    parejas.c.torneo == t.id)).all())
                tablas = [clasificar([p for p, g in grupo_de.items() if g == n],
                                     [self._resultado(p) for p in de_grupos if p.grupo == n])
                          for n in sorted(set(grupo_de.values()))]
                cabezas = cabezas_tras_grupos(tablas, f.pasan_por_grupo)
                self._crear_cuadro(c, t, f, [p for p, _ in cabezas], grupo_de)
                todos = c.execute(select(partidos).where(partidos.c.torneo == t.id)).all()
        cuadro = {(p.ronda, p.posicion): p for p in todos if p.fase == "cuadro"}
        if cuadro:
            n_rondas = max(r for r, _ in cuadro) + 1
            tercero = next((p for p in todos if p.fase == "tercero"), None)
            perdedores: list[int | None] = [None, None]
            for (ronda, pos), p in sorted(cuadro.items()):
                if p.estado != "terminado":
                    continue
                if ronda == n_rondas - 2 and tercero is not None:
                    perdedor = p.pareja_b if p.ganador == p.pareja_a else p.pareja_a
                    perdedores[pos] = perdedor  # None si fue un pase directo
                if ronda < n_rondas - 1:
                    self._colocar(c, cuadro[(ronda + 1, pos // 2)], pos % 2, p.ganador)
            if tercero is not None and tercero.estado == "esperando":
                semis = [cuadro[(n_rondas - 2, i)] for i in (0, 1)]
                if all(s.estado == "terminado" for s in semis):
                    a, b = perdedores
                    valores: dict[str, Any] = {"pareja_a": a, "pareja_b": b, "estado": "listo"}
                    if (a is None) != (b is None):
                        valores.update(estado="terminado", ganador=a or b, pase=True)
                    elif a is None:
                        valores.update(estado="terminado", pase=True)
                    c.execute(update(partidos).where(partidos.c.id == tercero.id).values(**valores))
        todos = c.execute(select(partidos).where(partidos.c.torneo == t.id)).all()
        if todos and all(p.estado == "terminado" for p in todos):
            campeon = None
            if f.tipo == "liga":
                ids = [fila.id for fila in c.execute(
                    select(parejas.c.id).where(parejas.c.torneo == t.id))]
                campeon = clasificar(ids, [self._resultado(p) for p in todos])[0].pareja
            else:
                final = next((p for p in todos if p.fase == "cuadro"
                              and p.ronda == max(q.ronda for q in todos if q.fase == "cuadro")),
                             None)
                campeon = final.ganador if final else None
            if campeon is not None:
                c.execute(update(torneos).where(torneos.c.id == t.id).values(
                    estado="terminado", campeon=campeon))

    def _colocar(self, c, p, hueco: int, pareja: int) -> None:
        """Pone a ``pareja`` en el hueco 0 (A) o 1 (B) del partido ``p`` del cuadro."""
        columna = "pareja_a" if hueco == 0 else "pareja_b"
        p = c.execute(select(partidos).where(partidos.c.id == p.id)).first()  # al día
        if getattr(p, columna) is not None:
            return
        otra = p.pareja_b if hueco == 0 else p.pareja_a
        c.execute(update(partidos).where(partidos.c.id == p.id).values(
            **{columna: pareja}, estado="listo" if otra is not None else "esperando"))

    @staticmethod
    def _resultado(p) -> Resultado:
        return Resultado(p.pareja_a, p.pareja_b, p.ganador, p.vacas_a, p.vacas_b,
                         p.tantos_a, p.tantos_b)

    # --- Consultas ------------------------------------------------------------------------

    def _torneo(self, c, codigo: str):
        t = c.execute(select(torneos).where(torneos.c.codigo == str(codigo)[:40])).first()
        if t is None:
            raise ErrorMesa("Ese torneo no existe (revisa el enlace de invitación)", 404)
        return t

    def _abierto(self, c, codigo: str):
        t = self._torneo(c, codigo)
        if t.estado != "inscripcion" or self.reloj() >= t.fecha_limite:
            raise ErrorMesa("La inscripción de este torneo está cerrada", 409)
        return t

    def _partido(self, c, t, partido_id: int):
        p = c.execute(select(partidos).where(partidos.c.id == partido_id,
                                             partidos.c.torneo == t.id)).first()
        if p is None:
            raise ErrorMesa("Ese partido no existe", 404)
        return p

    @staticmethod
    def _solo_organizador(t, usuario: Usuario) -> None:
        if t.organizador != usuario.id:
            raise ErrorMesa("Solo el organizador puede hacer eso", 403)

    @staticmethod
    def _pareja_de(c, torneo_id: int, usuario_id: int):
        return c.execute(select(parejas).where(
            parejas.c.torneo == torneo_id,
            or_(parejas.c.jugador1 == usuario_id, parejas.c.jugador2 == usuario_id))).first()

    @staticmethod
    def _confirmadas(c, torneo_id: int) -> int:
        return c.execute(select(func.count()).select_from(parejas).where(
            parejas.c.torneo == torneo_id, parejas.c.confirmada)).scalar_one()

    # --- Lo que ve cada uno ---------------------------------------------------------------

    def ver(self, usuario: Usuario, codigo: str) -> dict:
        """Todo el torneo tal como lo ve ``usuario``: inscripción, grupos, cuadro y números."""
        self._al_dia(codigo)
        with self.motor.connect() as c:
            t = self._torneo(c, codigo)
            filas = c.execute(select(parejas).where(parejas.c.torneo == t.id)
                              .order_by(parejas.c.creada)).all()
            todos = c.execute(select(partidos).where(partidos.c.torneo == t.id)
                              .order_by(partidos.c.id)).all()
            ids_usuarios = {t.organizador} | {u for p in filas for u in (p.jugador1, p.jugador2)}
            nombre_de = dict(c.execute(select(usuarios.c.id, usuarios.c.nombre).where(
                usuarios.c.id.in_(ids_usuarios))).all())
        organizo = t.organizador == usuario.id
        mia = next((p for p in filas if usuario.id in (p.jugador1, p.jugador2)), None)
        # Las parejas sin confirmar solo las ven sus jugadores y el organizador.
        visibles = [p for p in filas
                    if p.confirmada or organizo or usuario.id in (p.jugador1, p.jugador2)]
        confirmadas = [p.id for p in filas if p.confirmada]
        formato = Formato.desde_dict(t.formato)
        resuelto = Formato.desde_dict(t.resuelto) if t.resuelto else None
        datos = {
            "codigo": t.codigo, "nombre": t.nombre, "estado": t.estado,
            "fecha_limite": t.fecha_limite, "ahora": self.reloj(),
            "organizador": nombre_de[t.organizador], "organizo": organizo,
            "formato": formato.a_dict(), "resuelto": resuelto.a_dict() if resuelto else None,
            "descripcion": describir(formato, max(2, len(confirmadas))),
            "descripcion_lleno": describir(formato, formato.max_parejas),
            "yo": {"nombre": usuario.nombre, "pareja": mia.id if mia else None},
            "parejas": [{"id": p.id, "nombre": p.nombre, "confirmada": p.confirmada,
                         "jugadores": [nombre_de[p.jugador1], nombre_de[p.jugador2]],
                         "invitado_yo": p.jugador2 == usuario.id and not p.confirmada,
                         "grupo": p.grupo} for p in visibles],
            "campeon": t.campeon,
            "partidos": [self._partido_a_dict(p, mia) for p in todos],
        }
        if resuelto is not None:
            datos.update(self._tablas(resuelto, filas, todos))
        datos["estadisticas"] = self._estadisticas(filas, todos)
        return datos

    @staticmethod
    def _partido_a_dict(p, mia) -> dict:
        mio = mia is not None and mia.id in (p.pareja_a, p.pareja_b)
        return {"id": p.id, "fase": p.fase, "grupo": p.grupo, "jornada": p.jornada,
                "ronda": p.ronda, "posicion": p.posicion, "a": p.pareja_a, "b": p.pareja_b,
                "estado": p.estado, "ganador": p.ganador, "pase": p.pase,
                "vacas": [p.vacas_a, p.vacas_b], "tantos": [p.tantos_a, p.tantos_b],
                "mejor_de": p.mejor_de, "mio": mio,
                "puedo_jugar": mio and p.estado in ("listo", "jugando")}

    def _tablas(self, f: Formato, filas, todos) -> dict:
        """Grupos (con su tabla), liga y cuadro por rondas."""
        salida: dict[str, Any] = {"grupos": [], "liga": None, "cuadro": None}
        if f.tipo == "grupos":
            for g in sorted({p.grupo for p in filas if p.grupo is not None}):
                ids = [p.id for p in filas if p.grupo == g]
                jugados = [self._resultado(p) for p in todos
                           if p.fase == "grupos" and p.grupo == g and p.estado == "terminado"]
                salida["grupos"].append({
                    "numero": g, "nombre": f"Grupo {LETRAS[g % 26]}",
                    "pasan": f.pasan_por_grupo,
                    "tabla": [self._fila_a_dict(x) for x in clasificar(ids, jugados)]})
        if f.tipo == "liga":
            jugados = [self._resultado(p) for p in todos if p.estado == "terminado"]
            salida["liga"] = [self._fila_a_dict(x) for x in clasificar([p.id for p in filas],
                                                                      jugados)]
        cuadro = [p for p in todos if p.fase == "cuadro"]
        if cuadro:
            n_rondas = max(p.ronda for p in cuadro) + 1
            salida["cuadro"] = {"rondas": [
                {"nombre": nombre_ronda(2 ** (n_rondas - r)),
                 "partidos": [p.id for p in sorted(cuadro, key=lambda p: p.posicion)
                              if p.ronda == r]}
                for r in range(n_rondas)],
                "tercero": next((p.id for p in todos if p.fase == "tercero"), None)}
        return salida

    @staticmethod
    def _fila_a_dict(x) -> dict:
        return {"pareja": x.pareja, "jugados": x.jugados, "ganados": x.ganados,
                "perdidos": x.perdidos, "vacas": [x.vacas_favor, x.vacas_contra],
                "tantos": [x.tantos_favor, x.tantos_contra], "puntos": x.puntos}

    @staticmethod
    def _estadisticas(filas, todos) -> list[dict]:
        """Números de cada pareja en todo el torneo (los pases y w.o. no cuentan en las
        estadísticas de juego, solo en partidos ganados)."""
        acum: dict[int, dict] = defaultdict(lambda: {
            "jugados": 0, "ganados": 0, "vacas": [0, 0], "tantos": [0, 0], "manos": 0,
            "ordagos": 0, "ordagos_ganados": 0, "envites": 0})
        for p in todos:
            if p.estado != "terminado" or p.pareja_a is None or p.pareja_b is None:
                continue
            for pareja, propio, ajeno in ((p.pareja_a, "a", "b"), (p.pareja_b, "b", "a")):
                e = acum[pareja]
                e["jugados"] += 1
                e["ganados"] += p.ganador == pareja
                e["vacas"][0] += p.vacas_a if propio == "a" else p.vacas_b
                e["vacas"][1] += p.vacas_b if propio == "a" else p.vacas_a
                if p.estadisticas:
                    yo, el = p.estadisticas[propio], p.estadisticas[ajeno]
                    e["tantos"][0] += yo["tantos"]
                    e["tantos"][1] += el["tantos"]
                    for clave in ("manos", "ordagos", "ordagos_ganados", "envites"):
                        e[clave] += yo[clave]
        return [{"pareja": p.id, **acum[p.id]} for p in filas if p.confirmada]

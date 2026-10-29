"""Cuentas de usuario: registro, inicio de sesión y sesiones.

- **Contraseñas:** nunca se guardan. Se guarda su hash con **scrypt** (de la librería estándar),
  con una sal aleatoria por usuario. scrypt es lento a propósito y gasta memoria, así que probar
  millones de contraseñas contra una base de datos robada sale carísimo.
- **Sesiones:** al entrar, el navegador recibe un código aleatorio en una cookie ``HttpOnly``
  (el JavaScript de la página no la puede leer) y ``SameSite=Lax`` (otra web no puede hacer
  peticiones con ella). En la base de datos solo se guarda el hash del código: quien la lea no
  puede hacerse pasar por nadie.
- **Fuerza bruta:** tras varios intentos fallidos con un mismo usuario, se bloquea un rato.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine, delete, insert, select

from musarena.web.bd import sesiones, usuarios
from musarena.web.mesas import ErrorMesa

#: Duración de una sesión (segundos).
DURACION_SESION = 30 * 24 * 3600
MIN_CLAVE, MAX_CLAVE = 8, 128
MIN_NOMBRE, MAX_NOMBRE = 3, 20
#: Intentos fallidos seguidos permitidos por usuario antes de bloquearlo un rato.
MAX_FALLOS, BLOQUEO = 8, 15 * 60
#: Parámetros de scrypt (2^14 · 8 · 128 B = 16 MB por cálculo, unos 50 ms).
_N, _R, _P = 2**14, 8, 1


@dataclass(frozen=True)
class Usuario:
    id: int
    nombre: str


def hash_clave(clave: str, sal: bytes | None = None) -> str:
    """Hash de una contraseña con su sal, en una sola cadena (``scrypt$n$r$p$sal$hash``)."""
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(clave.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${h.hex()}"


def comprobar_clave(clave: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calculado = hashlib.scrypt(clave.encode("utf-8"), salt=bytes.fromhex(sal), n=int(n),
                                   r=int(r), p=int(p), dklen=len(h) // 2)
    except ValueError:
        return False
    return hmac.compare_digest(calculado.hex(), h)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validar_nombre(nombre: object) -> str:
    """Nombre de usuario limpio, o ``ErrorMesa`` si no vale.

    Letras (con tildes), números, ``_``, ``-`` y ``.``; sin espacios, para que nadie se pueda
    hacer pasar por otro con un nombre que se ve igual.
    """
    if not isinstance(nombre, str):
        raise ErrorMesa("Falta el nombre de usuario")
    nombre = unicodedata.normalize("NFC", nombre.strip())
    if not MIN_NOMBRE <= len(nombre) <= MAX_NOMBRE:
        raise ErrorMesa(f"El nombre de usuario tiene que tener de {MIN_NOMBRE} a {MAX_NOMBRE} "
                        "caracteres")
    if not all(c.isalnum() or c in "_-." for c in nombre):
        raise ErrorMesa("El nombre de usuario solo puede tener letras, números, _, - y .")
    return nombre


class Cuentas:
    """Registro, entrada y sesiones sobre la base de datos."""

    def __init__(self, motor: Engine, reloj: Callable[[], float] = time.time) -> None:
        self.motor = motor
        self.reloj = reloj
        self._fallos: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    # --- Registro y entrada ---------------------------------------------------------------

    def registrar(self, nombre: object, clave: object) -> tuple[Usuario, str]:
        """Crea la cuenta y abre una sesión. Devuelve el usuario y el código de la sesión."""
        nombre = validar_nombre(nombre)
        if not isinstance(clave, str) or not MIN_CLAVE <= len(clave) <= MAX_CLAVE:
            raise ErrorMesa(f"La contraseña tiene que tener de {MIN_CLAVE} a {MAX_CLAVE} "
                            "caracteres")
        if clave.strip().lower() == nombre.lower():
            raise ErrorMesa("La contraseña no puede ser tu nombre de usuario")
        guardada = hash_clave(clave)
        with self.motor.begin() as c:
            if c.execute(select(usuarios.c.id).where(
                    usuarios.c.nombre_clave == nombre.lower())).first():
                raise ErrorMesa("Ese nombre de usuario ya existe", 409)
            uid = c.execute(insert(usuarios).values(
                nombre=nombre, nombre_clave=nombre.lower(), clave=guardada,
                creado=self.reloj())).inserted_primary_key[0]
        usuario = Usuario(uid, nombre)
        return usuario, self.abrir_sesion(usuario)

    def entrar(self, nombre: object, clave: object) -> tuple[Usuario, str]:
        """Comprueba la contraseña y abre una sesión."""
        if not isinstance(nombre, str) or not isinstance(clave, str) or len(clave) > MAX_CLAVE:
            raise ErrorMesa("Usuario o contraseña incorrectos", 401)
        clave_usuario = nombre.strip().lower()
        self._comprobar_bloqueo(clave_usuario)
        with self.motor.connect() as c:
            fila = c.execute(select(usuarios).where(
                usuarios.c.nombre_clave == clave_usuario)).first()
        # Se calcula el hash aunque el usuario no exista: así la respuesta tarda lo mismo y
        # no delata qué nombres están registrados.
        guardada = fila.clave if fila else hash_clave("x" * MIN_CLAVE, b"\0" * 16)
        if not comprobar_clave(clave, guardada) or fila is None:
            self._apuntar_fallo(clave_usuario)
            raise ErrorMesa("Usuario o contraseña incorrectos", 401)
        with self._lock:
            self._fallos.pop(clave_usuario, None)
        usuario = Usuario(fila.id, fila.nombre)
        return usuario, self.abrir_sesion(usuario)

    def _comprobar_bloqueo(self, nombre: str) -> None:
        ahora = self.reloj()
        with self._lock:
            recientes = [t for t in self._fallos.get(nombre, []) if ahora - t < BLOQUEO]
            self._fallos[nombre] = recientes
        if len(recientes) >= MAX_FALLOS:
            minutos = int((BLOQUEO - (ahora - recientes[0])) // 60) + 1
            raise ErrorMesa(f"Demasiados intentos fallidos: prueba dentro de {minutos} min", 429)

    def _apuntar_fallo(self, nombre: str) -> None:
        with self._lock:
            self._fallos.setdefault(nombre, []).append(self.reloj())
            if len(self._fallos) > 10_000:  # que no crezca sin fin
                self._fallos.clear()

    # --- Sesiones -------------------------------------------------------------------------

    def abrir_sesion(self, usuario: Usuario) -> str:
        token = secrets.token_urlsafe(32)
        ahora = self.reloj()
        with self.motor.begin() as c:
            c.execute(delete(sesiones).where(sesiones.c.expira < ahora))
            c.execute(insert(sesiones).values(token=_hash_token(token), usuario=usuario.id,
                                              expira=ahora + DURACION_SESION))
        return token

    def usuario(self, token: str | None) -> Usuario | None:
        """El usuario de una sesión abierta, o ``None``."""
        if not token or len(token) > 100:
            return None
        with self.motor.connect() as c:
            fila = c.execute(
                select(usuarios.c.id, usuarios.c.nombre, sesiones.c.expira)
                .join(sesiones, sesiones.c.usuario == usuarios.c.id)
                .where(sesiones.c.token == _hash_token(token))).first()
        if fila is None or fila.expira < self.reloj():
            return None
        return Usuario(fila.id, fila.nombre)

    def cerrar_sesion(self, token: str | None) -> None:
        if token:
            with self.motor.begin() as c:
                c.execute(delete(sesiones).where(sesiones.c.token == _hash_token(token)))

    def buscar(self, nombre: str) -> Usuario | None:
        """Usuario por su nombre (sin distinguir mayúsculas)."""
        if not isinstance(nombre, str):
            return None
        with self.motor.connect() as c:
            fila = c.execute(select(usuarios.c.id, usuarios.c.nombre).where(
                usuarios.c.nombre_clave == nombre.strip().lower())).first()
        return Usuario(fila.id, fila.nombre) if fila else None

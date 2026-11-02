"""Cuentas de usuario: registro, inicio de sesión y sesiones.

- **Contraseñas:** nunca se guardan. Se guarda su hash con **scrypt** (de la librería estándar),
  con una sal aleatoria por usuario. scrypt es lento a propósito y gasta memoria, así que probar
  millones de contraseñas contra una base de datos robada sale carísimo.
- **Sesiones:** al entrar, el navegador recibe un código aleatorio en una cookie ``HttpOnly``
  (el JavaScript de la página no la puede leer) y ``SameSite=Lax`` (otra web no puede hacer
  peticiones con ella). En la base de datos solo se guarda el hash del código: quien la lea no
  puede hacerse pasar por nadie.
- **Fuerza bruta:** tras varios intentos fallidos con un usuario **desde una misma dirección**,
  esa dirección se bloquea un rato para ese usuario; y cada dirección tiene además un tope de
  fallos en total. Así nadie puede dejar a otro sin entrar (se bloquearía solo a sí mismo).
  El intento se apunta **antes** de comprobar la contraseña, así que lanzar muchos a la vez no
  sirve para probar más de la cuenta.
- **Qué usuarios existen** no es un secreto (los nombres se ven en los torneos y el registro
  dice si uno está cogido); aun así, entrar tarda lo mismo exista o no el usuario.
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
from sqlalchemy.exc import IntegrityError

from musarena.web.bd import sesiones, usuarios
from musarena.web.mesas import ErrorMesa

#: Duración de una sesión (segundos).
DURACION_SESION = 30 * 24 * 3600
MIN_CLAVE, MAX_CLAVE = 8, 128
MIN_NOMBRE, MAX_NOMBRE = 3, 20
#: Intentos fallidos permitidos por usuario y dirección, y por dirección en total, antes de
#: bloquear un rato.
MAX_FALLOS, MAX_FALLOS_IP, BLOQUEO = 8, 30, 15 * 60
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


#: Hash con el que se compara cuando el usuario no existe (se calcula una vez): así entrar
#: tarda lo mismo, un solo scrypt, exista o no.
_RELLENO = hash_clave("x" * MIN_CLAVE, b"\0" * 16)


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
        self._en_curso: dict[str, int] = {}  # intentos reservados que aún se comprueban
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
        cogido = ErrorMesa("Ese nombre de usuario ya existe", 409)
        try:
            with self.motor.begin() as c:
                if c.execute(select(usuarios.c.id).where(
                        usuarios.c.nombre_clave == nombre.lower())).first():
                    raise cogido
                uid = c.execute(insert(usuarios).values(
                    nombre=nombre, nombre_clave=nombre.lower(), clave=guardada,
                    creado=self.reloj())).inserted_primary_key[0]
        except IntegrityError:  # otro lo ha registrado justo a la vez (la columna es única)
            raise cogido from None
        usuario = Usuario(uid, nombre)
        return usuario, self.abrir_sesion(usuario)

    def entrar(self, nombre: object, clave: object, ip: str = "") -> tuple[Usuario, str]:
        """Comprueba la contraseña y abre una sesión (``ip``: de dónde llega el intento)."""
        if not isinstance(nombre, str) or not isinstance(clave, str) or len(clave) > MAX_CLAVE:
            raise ErrorMesa("Usuario o contraseña incorrectos", 401)
        clave_usuario = nombre.strip().lower()
        limites = {f"u:{clave_usuario}|{ip}": MAX_FALLOS, f"ip:{ip}": MAX_FALLOS_IP}
        self._reservar(limites)
        try:
            with self.motor.connect() as c:
                fila = c.execute(select(usuarios).where(
                    usuarios.c.nombre_clave == clave_usuario)).first()
            coincide = comprobar_clave(clave, fila.clave if fila else _RELLENO)  # siempre uno
            correcta = coincide and fila is not None
            with self._lock:
                if correcta:
                    self._fallos.pop(f"u:{clave_usuario}|{ip}", None)
                else:
                    for k in limites:
                        self._fallos.setdefault(k, []).append(self.reloj())
        finally:
            with self._lock:
                for k in limites:
                    self._en_curso[k] -= 1
                    if not self._en_curso[k]:
                        del self._en_curso[k]
        if not correcta:
            raise ErrorMesa("Usuario o contraseña incorrectos", 401)
        usuario = Usuario(fila.id, fila.nombre)
        return usuario, self.abrir_sesion(usuario)

    def _reservar(self, limites: dict[str, int]) -> None:
        """Cuenta el intento antes de comprobar nada, dentro del cerrojo: los intentos a la vez
        no se cuelan. Si ya se ha llegado al tope, error 429."""
        ahora = self.reloj()
        with self._lock:
            if len(self._fallos) > 10_000:  # que no crezca sin fin: fuera solo lo caducado
                self._fallos = {k: v for k, v in self._fallos.items()
                                if v and ahora - v[-1] < BLOQUEO}
            for k, maximo in limites.items():
                recientes = [t for t in self._fallos.get(k, []) if ahora - t < BLOQUEO]
                self._fallos[k] = recientes
                if len(recientes) + self._en_curso.get(k, 0) >= maximo:
                    espera = BLOQUEO - (ahora - recientes[0]) if recientes else 60
                    raise ErrorMesa("Demasiados intentos fallidos: prueba dentro de "
                                    f"{int(espera // 60) + 1} min", 429)
            for k in limites:
                self._en_curso[k] = self._en_curso.get(k, 0) + 1

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

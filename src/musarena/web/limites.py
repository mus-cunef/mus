"""Límites por cliente: que un solo visitante no pueda acaparar el servidor.

- :func:`ip_cliente`: la dirección de quien hace la petición. Detrás del proxy de Render es la
  **última** de ``X-Forwarded-For`` (la que añade el proxy); las anteriores las puede escribir
  el propio cliente, así que no valen para limitar.
- :class:`Ventana`: cuántas veces ha hecho algo cada cliente en los últimos segundos.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fastapi import Request

#: Claves que se recuerdan como mucho (después se olvidan las que llevan más tiempo quietas).
MAX_CLAVES = 10_000


def ip_cliente(request: Request, detras_de_proxy: bool) -> str:
    if detras_de_proxy:
        reenviada = request.headers.get("x-forwarded-for", "")
        ultima = reenviada.rsplit(",", 1)[-1].strip()
        if ultima:
            return ultima
    return request.client.host if request.client else "?"


class Ventana:
    """Permite ``maximo`` veces por clave en cada ``segundos`` (``maximo`` 0 = sin límite)."""

    def __init__(self, maximo: int, segundos: float,
                 reloj: Callable[[], float] = time.monotonic) -> None:
        self.maximo = maximo
        self.segundos = segundos
        self.reloj = reloj
        self._veces: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def permitir(self, clave: str) -> bool:
        """Apunta una vez más para ``clave`` si cabe; si no, devuelve ``False``."""
        if self.maximo <= 0:
            return True
        ahora = self.reloj()
        with self._lock:
            veces = [t for t in self._veces.get(clave, []) if ahora - t < self.segundos]
            if len(veces) >= self.maximo:
                self._veces[clave] = veces
                return False
            veces.append(ahora)
            self._veces[clave] = veces
            if len(self._veces) > MAX_CLAVES:
                self._olvidar(ahora)
            return True

    def _olvidar(self, ahora: float) -> None:
        """Quita las claves caducadas y, si aún sobran, las que llevan más tiempo quietas."""
        self._veces = {k: v for k, v in self._veces.items() if ahora - v[-1] < self.segundos}
        if len(self._veces) > MAX_CLAVES:
            por_antiguedad = sorted(self._veces, key=lambda k: self._veces[k][-1])
            for k in por_antiguedad[: len(self._veces) - MAX_CLAVES]:
                del self._veces[k]

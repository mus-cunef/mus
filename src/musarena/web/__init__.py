"""Interfaz web de Mus Arena: jugar desde el navegador y lanzar torneos.

- :mod:`~musarena.web.config`: límites y opciones (modo local o modo internet).
- :mod:`~musarena.web.vista`: lo que se manda al navegador de cada jugador (solo su
  :class:`~musarena.observation.Observation`, nunca el estado completo).
- :mod:`~musarena.web.mesas`: las mesas en juego (partidas con humanos y bots).
- :mod:`~musarena.web.torneos`: torneos lanzados desde la web, con su progreso.
- :mod:`~musarena.web.app`: la aplicación FastAPI (API y páginas).

Se arranca con ``mus-web`` (necesita el extra ``[web]``: ``pip install -e ".[web]"``).
"""

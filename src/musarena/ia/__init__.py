"""Bot inteligente: una red neuronal que decide a partir de la observación.

- :mod:`~musarena.ia.acciones`: catálogo fijo de acciones que puede elegir la red.
- :mod:`~musarena.ia.codificacion`: traduce una :class:`~musarena.observation.Observation` a
  un vector de números.
- :mod:`~musarena.ia.red`: la red neuronal, que para jugar solo necesita numpy.
- :mod:`~musarena.ia.entrenamiento`: generación de datos y entrenamiento (necesita PyTorch:
  ``pip install -e ".[ia]"``).

Jugar con el bot no requiere PyTorch; entrenarlo, sí.
"""

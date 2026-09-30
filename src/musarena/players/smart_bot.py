"""Bot inteligente: juega con una red neuronal entrenada (ver :mod:`musarena.ia`)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from musarena.actions import Action
from musarena.ia import acciones
from musarena.ia.codificacion import N_ENTRADAS, codificar
from musarena.ia.red import Red
from musarena.observation import Observation
from musarena.player import Bot

#: Modelo que se usa si no se indica otro.
MODELO_POR_DEFECTO = Path(__file__).resolve().parent.parent / "ia" / "modelos" / "inteligente.npz"


class SmartBot(Bot):
    """Elige la acción con la red neuronal.

    - ``modelo``: ruta a un ``.npz`` o una :class:`~musarena.ia.red.Red` ya cargada.
    - ``temperatura``: 0 elige siempre la acción más probable; más de 0 elige al azar según las
      probabilidades de la red (más variado, más "humano"; 1 es la distribución tal cual).
    """

    tipo = "inteligente"
    descripcion = "Red neuronal entrenada: imita a los mejores y aprende jugando"

    def __init__(
        self,
        nombre: str | None = None,
        seed: int | None = None,
        modelo: str | Path | Red | None = None,
        temperatura: float = 0.0,
    ) -> None:
        super().__init__(nombre, seed)
        red = modelo if isinstance(modelo, Red) else Red.cargar(modelo or MODELO_POR_DEFECTO)
        if red.n_entradas != N_ENTRADAS:
            raise ValueError(
                f"El modelo espera {red.n_entradas} entradas y la codificación tiene "
                f"{N_ENTRADAS}: hay que reentrenarlo"
            )
        self.red = red
        self.temperatura = temperatura
        self.razon = ""

    def probabilidades(self, observation: Observation, legal_actions: Sequence[Action]
                       ) -> tuple[np.ndarray, np.ndarray, float]:
        """(máscara de legales, probabilidad de cada acción del catálogo, valor estimado)."""
        mascara = acciones.mascara(legal_actions, observation.cartas)
        p, v = self.red.evaluar(codificar(observation), mascara)
        return mascara, p, v

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        mascara, p, v = self.probabilidades(observation, legal_actions)
        if not mascara.any():  # no debería pasar: el catálogo cubre todas las fases
            self.razon = "sin acciones del catálogo: primera legal"
            return legal_actions[0]
        if self.temperatura > 0:
            q = np.where(mascara, p ** (1 / self.temperatura), 0.0)
            i = int(self.rng.choices(range(len(q)), weights=q)[0])
        else:
            i = int(np.argmax(p))
        mejores = np.argsort(-p)[:3]
        self.razon = (f"valor {v:+.2f}; " + ", ".join(
            f"{acciones.NOMBRES[j]} {p[j]:.0%}" for j in mejores if p[j] > 0))
        return acciones.accion(i, observation.cartas)

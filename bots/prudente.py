"""Bot de ejemplo para el torneo: muy prudente, solo apuesta con manos muy buenas.

Sirve de plantilla para programar un bot propio sin tocar la librería: copia este archivo en
``bots/``, cambia el nombre de la clase y ``tipo``, y entrará solo en el torneo
(``mus-torneo``) y en la arena (``mus-arena bots/mi_bot.py reglas``).
"""

from musarena.actions import Descarte, Envido, Mus, NoHayMus, NoQuiero, Paso, Quiero
from musarena.estrategia.tipos import FUERZA, indice_de
from musarena.estrategia.valor import PERCENTIL
from musarena.player import Bot


class Prudente(Bot):
    tipo = "prudente"
    descripcion = "Ejemplo: corta con buena mano y solo envida o quiere con manos muy fuertes"

    def choose_action(self, observation, legal_actions):
        # Lo único que recibe un bot: su Observation (sus cartas e información pública) y
        # la lista de acciones legales. Tiene que devolver una de ellas.
        tipo = indice_de(observation.cartas)
        if Mus() in legal_actions:
            return NoHayMus() if PERCENTIL[tipo] > 0.6 else Mus()
        if isinstance(legal_actions[0], Descarte):
            # Se queda las figuras (sota, caballo, rey) y tira el resto (o todo si no hay).
            tirar = [c for c in observation.cartas if c.rango < 10]
            return Descarte(frozenset(tirar or observation.cartas))
        fuerza = FUERZA[observation.lance][tipo]
        if Quiero() in legal_actions:
            return Quiero() if fuerza > 0.8 else NoQuiero()
        if fuerza > 0.85 and Envido() in legal_actions:
            return Envido()
        return Paso()
